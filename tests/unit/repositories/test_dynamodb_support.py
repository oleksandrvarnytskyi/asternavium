# SPDX-License-Identifier: AGPL-3.0-or-later
import logging
import threading
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, NoReturn, cast

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from ulid import ULID

from app.core.errors import StorageUnavailableError
from app.repositories.app_table import SORT_KEY
from app.repositories.dynamodb_support import (
    ConditionFailedError,
    Item,
    key_item,
    number_value,
    query_page,
    read_float,
    read_int,
    read_optional_string,
    read_timestamp,
    run_dynamodb,
    string_value,
    timestamp_value,
)
from app.repositories.keys import SESSION_PREFIX, encode_cursor, session_key, user_key

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient

pytestmark = pytest.mark.anyio

# Contains a user ID, so it must never appear in logs.
USER_PARTITION = user_key("alice")


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "test"}}, "Query")


def _raise(error: Exception) -> NoReturn:
    raise error


class _StubQueryClient:
    """Answers ``query`` with a fixed response, as DynamoDB does for a 1 MB-truncated page."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.response


def _session_item(session_id: str) -> Item:
    return key_item(USER_PARTITION, session_key(session_id))


async def test_run_dynamodb_runs_call_in_worker_thread() -> None:
    event_loop_thread = threading.get_ident()

    call_thread = await run_dynamodb("GetItem", threading.get_ident)

    assert call_thread != event_loop_thread


async def test_run_dynamodb_translates_failed_condition() -> None:
    with pytest.raises(ConditionFailedError):
        await run_dynamodb(
            "PutItem", lambda: _raise(_client_error("ConditionalCheckFailedException"))
        )


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(_client_error("ThrottlingException"), id="throttling"),
        pytest.param(_client_error("ProvisionedThroughputExceededException"), id="throughput"),
        pytest.param(_client_error("InternalServerError"), id="server-error"),
        pytest.param(EndpointConnectionError(endpoint_url="https://dynamodb"), id="network"),
    ],
)
async def test_run_dynamodb_translates_transient_failure(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING), pytest.raises(StorageUnavailableError) as caught:
        await run_dynamodb("Query", lambda: _raise(error))

    assert caught.value.code == "storage_unavailable"
    assert "DynamoDB Query failed" in caplog.text


async def test_run_dynamodb_reraises_error_that_indicates_a_bug() -> None:
    with pytest.raises(ClientError, match="ValidationException"):
        await run_dynamodb("Query", lambda: _raise(_client_error("ValidationException")))


async def test_run_dynamodb_logs_no_keys(caplog: pytest.LogCaptureFixture) -> None:
    error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": USER_PARTITION}}, "Query"
    )

    with caplog.at_level(logging.WARNING), pytest.raises(StorageUnavailableError):
        await run_dynamodb("Query", lambda: _raise(error))

    assert USER_PARTITION not in caplog.text


def test_timestamp_value_stores_utc_iso_string() -> None:
    kyiv_summer = timezone(timedelta(hours=3))

    value = timestamp_value(datetime(2026, 7, 1, 12, 0, tzinfo=kyiv_summer))

    assert value == {"S": "2026-07-01T09:00:00+00:00"}


def test_timestamp_value_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        timestamp_value(datetime(2026, 7, 1, 12, 0))  # noqa: DTZ001 - the naive input under test


def test_attribute_values_round_trip() -> None:
    moment = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    item: Item = {
        "count": number_value(3),
        "latitude": number_value(50.45466),
        "at": timestamp_value(moment),
    }

    assert read_int(item, "count") == 3
    assert read_float(item, "latitude") == 50.45466
    assert read_timestamp(item, "at") == moment


def test_read_optional_string_handles_present_and_missing_attribute() -> None:
    item: Item = {"name": string_value("x")}

    assert read_optional_string(item, "name") == "x"
    assert read_optional_string(item, "missing") is None


@pytest.mark.parametrize("limit", [0, -1])
async def test_query_page_rejects_non_positive_limit(limit: int) -> None:
    client = cast("DynamoDBClient", _StubQueryClient({"Items": []}))

    with pytest.raises(ValueError, match="positive"):
        await query_page(
            client,
            "table",
            partition_key=USER_PARTITION,
            sort_prefix=SESSION_PREFIX,
            limit=limit,
            cursor=None,
        )


async def test_query_page_continues_after_response_cut_at_size_limit() -> None:
    session_ids = [str(ULID()), str(ULID())]
    truncated = {
        "Items": [_session_item(session_id) for session_id in session_ids],
        "LastEvaluatedKey": _session_item(session_ids[-1]),
    }
    stub = _StubQueryClient(truncated)

    items, next_cursor = await query_page(
        cast("DynamoDBClient", stub),
        "table",
        partition_key=USER_PARTITION,
        sort_prefix=SESSION_PREFIX,
        limit=10,
        cursor=None,
    )

    assert len(items) == 2
    assert next_cursor == encode_cursor(items[-1][SORT_KEY]["S"])
    assert stub.calls[0]["Limit"] == 11
    assert stub.calls[0]["ScanIndexForward"] is False
