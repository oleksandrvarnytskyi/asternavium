# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plumbing shared by the DynamoDB repositories.

Runs blocking ``boto3`` calls in a worker thread (decision D6), translates failures into domain
errors, converts attribute values, and reads one page of a query.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import anyio.to_thread
from botocore.exceptions import BotoCoreError, ClientError

from app.core.errors import StorageUnavailableError
from app.repositories.app_table import PARTITION_KEY, SORT_KEY
from app.repositories.keys import decode_cursor, encode_cursor

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_dynamodb.type_defs import AttributeValueTypeDef, QueryInputTypeDef

logger = logging.getLogger(__name__)

type Item = dict[str, AttributeValueTypeDef]

CONDITIONAL_CHECK_FAILED: Final = "ConditionalCheckFailedException"
# Error codes that mean "busy or broken, try later", as opposed to a bug in the request.
_TRANSIENT_ERROR_CODES: Final = frozenset(
    {
        "InternalServerError",
        "ProvisionedThroughputExceededException",
        "RequestLimitExceeded",
        "ServiceUnavailable",
        "ThrottlingException",
    }
)
_STORAGE_UNAVAILABLE_MESSAGE: Final = "Storage is temporarily unavailable; try again shortly."
# Placeholders for the key attributes, so expressions never contain raw attribute names.
KEY_NAMES: Final = {"#pk": PARTITION_KEY, "#sk": SORT_KEY}


class ConditionFailedError(Exception):
    """A conditional write's condition did not hold; repositories turn it into a domain error."""


def storage_unavailable() -> StorageUnavailableError:
    """Return the error raised when the database cannot serve a request right now."""
    return StorageUnavailableError(_STORAGE_UNAVAILABLE_MESSAGE)


async def run_dynamodb[T](operation: str, call: Callable[[], T]) -> T:
    """Run a blocking ``boto3`` call in a worker thread and translate its failures.

    The client has already retried transient failures (see :mod:`app.repositories.dynamodb`).

    :param operation: DynamoDB operation name for logs, e.g. ``"Query"``. Logs never include
        keys or values, because keys contain user IDs.
    :param call: The ``boto3`` call, without arguments.
    :raises ConditionFailedError: If a conditional write's condition did not hold.
    :raises StorageUnavailableError: On throttling, server errors, timeouts or network errors.
    :raises botocore.exceptions.ClientError: On any other error, which indicates a bug.
    """
    try:
        return await anyio.to_thread.run_sync(call)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == CONDITIONAL_CHECK_FAILED:
            raise ConditionFailedError from exc
        if code not in _TRANSIENT_ERROR_CODES:
            raise
        logger.warning("DynamoDB %s failed: %s", operation, code)
        raise storage_unavailable() from exc
    except BotoCoreError as exc:
        logger.warning("DynamoDB %s failed: %s", operation, type(exc).__name__)
        raise storage_unavailable() from exc


def string_value(value: str) -> "AttributeValueTypeDef":
    """Return a string attribute."""
    return {"S": value}


def number_value(value: int | float) -> "AttributeValueTypeDef":
    """Return a number attribute; floats keep their shortest round-trip representation."""
    return {"N": str(value)}


def timestamp_value(value: datetime) -> "AttributeValueTypeDef":
    """Return an ISO 8601 UTC string attribute, e.g. ``2026-11-05T09:30:00+00:00``.

    :raises ValueError: If ``value`` is naive.
    """
    if value.tzinfo is None:
        msg = "timestamps must be timezone-aware"
        raise ValueError(msg)
    return string_value(value.astimezone(UTC).isoformat())


def read_string(item: Item, name: str) -> str:
    """Read a required string attribute."""
    return item[name]["S"]


def read_optional_string(item: Item, name: str) -> str | None:
    """Read a string attribute that may be absent."""
    value = item.get(name)
    return None if value is None else value["S"]


def read_int(item: Item, name: str) -> int:
    """Read a required integer attribute."""
    return int(item[name]["N"])


def read_float(item: Item, name: str) -> float:
    """Read a required number attribute as a float."""
    return float(item[name]["N"])


def read_timestamp(item: Item, name: str) -> datetime:
    """Read a timestamp written by :func:`timestamp_value` as an aware UTC datetime."""
    return datetime.fromisoformat(read_string(item, name))


def key_item(partition_key: str, sort_key: str) -> Item:
    """Return the primary key of an item."""
    return {PARTITION_KEY: string_value(partition_key), SORT_KEY: string_value(sort_key)}


def prefix_query(table_name: str, *, partition_key: str, sort_prefix: str) -> "QueryInputTypeDef":
    """Return a query for the items under a partition key whose sort keys share a prefix."""
    return {
        "TableName": table_name,
        "KeyConditionExpression": "#pk = :pk AND begins_with(#sk, :prefix)",
        "ExpressionAttributeNames": dict(KEY_NAMES),
        "ExpressionAttributeValues": {
            ":pk": string_value(partition_key),
            ":prefix": string_value(sort_prefix),
        },
    }


async def query_page(
    client: "DynamoDBClient",
    table_name: str,
    *,
    partition_key: str,
    sort_prefix: str,
    limit: int,
    cursor: str | None,
) -> tuple[list[Item], str | None]:
    """Read one page of items under a partition key and sort key prefix, newest first.

    Asks for one item more than ``limit`` to know whether another page exists, so the last page
    never carries a cursor to an empty page.

    :param limit: Maximum items on the page; positive.
    :returns: The page's items and the cursor of the next page, or ``None`` on the last page.
    :raises ValueError: If ``limit`` is not positive.
    :raises InvalidCursorError: If ``cursor`` was not issued for this list.
    """
    if limit < 1:
        msg = "limit must be positive"
        raise ValueError(msg)
    query = prefix_query(table_name, partition_key=partition_key, sort_prefix=sort_prefix)
    query["ScanIndexForward"] = False
    query["Limit"] = limit + 1
    if cursor is not None:
        query["ExclusiveStartKey"] = key_item(
            partition_key, decode_cursor(cursor, prefix=sort_prefix)
        )
    response = await run_dynamodb("Query", lambda: client.query(**query))
    items = response["Items"]
    # A response cut at 1 MB has fewer items than asked for but still a LastEvaluatedKey.
    has_more = len(items) > limit or ("LastEvaluatedKey" in response and bool(items))
    page = items[:limit]
    next_cursor = encode_cursor(read_string(page[-1], SORT_KEY)) if has_more else None
    return page, next_cursor
