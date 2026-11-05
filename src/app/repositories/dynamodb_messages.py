# SPDX-License-Identifier: AGPL-3.0-or-later
"""Chat messages in the DynamoDB app table."""

import functools
import logging
from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Final

import anyio

from app.domain.chat import MessageRole
from app.repositories.app_table import PARTITION_KEY, SORT_KEY
from app.repositories.dynamodb_support import (
    ConditionFailedError,
    Item,
    key_item,
    prefix_query,
    query_page,
    read_string,
    read_timestamp,
    run_dynamodb,
    storage_unavailable,
    string_value,
    timestamp_value,
)
from app.repositories.keys import (
    MESSAGE_PREFIX,
    SESSION_PREFIX,
    id_from_key,
    message_key,
    session_key,
)
from app.repositories.records import MessageRecord, Page

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_dynamodb.type_defs import WriteRequestUnionTypeDef

logger = logging.getLogger(__name__)

# DynamoDB accepts at most 25 requests per BatchWriteItem call.
MAX_BATCH_WRITE_ITEMS: Final = 25
# Retries for items DynamoDB left unprocessed under load, with doubling waits from the base.
MAX_UNPROCESSED_RETRIES: Final = 5
UNPROCESSED_RETRY_BASE_SECONDS: Final = 0.05
_DUPLICATE_MESSAGE_MESSAGE: Final = "A message with this ID already exists."
_KEYS_ONLY: Final = "#pk, #sk"


class _Attribute(StrEnum):
    """Attribute names of a message item besides its keys."""

    ROLE = "role"
    CONTENT = "content"
    CREATED_AT = "created_at"


def _to_item(message: MessageRecord) -> Item:
    return key_item(session_key(message.session_id), message_key(message.message_id)) | {
        _Attribute.ROLE: string_value(message.role),
        _Attribute.CONTENT: string_value(message.content),
        _Attribute.CREATED_AT: timestamp_value(message.created_at),
    }


def _from_item(item: Item) -> MessageRecord:
    return MessageRecord(
        session_id=id_from_key(read_string(item, PARTITION_KEY), SESSION_PREFIX),
        message_id=id_from_key(read_string(item, SORT_KEY), MESSAGE_PREFIX),
        role=MessageRole(read_string(item, _Attribute.ROLE)),
        content=read_string(item, _Attribute.CONTENT),
        created_at=read_timestamp(item, _Attribute.CREATED_AT),
    )


class DynamoDBMessageRepository:
    """:class:`~app.repositories.protocols.MessageRepository` on the app table.

    Messages are keyed by session only; the caller checks session ownership first.
    """

    def __init__(self, client: "DynamoDBClient", table_name: str) -> None:
        self._client = client
        self._table_name = table_name

    async def add(self, message: MessageRecord) -> None:
        """Store a new message.

        :raises ValueError: If a message with this ID already exists in the session.
        """
        item = _to_item(message)
        try:
            await run_dynamodb(
                "PutItem",
                lambda: self._client.put_item(
                    TableName=self._table_name,
                    Item=item,
                    ConditionExpression="attribute_not_exists(#pk)",
                    ExpressionAttributeNames={"#pk": PARTITION_KEY},
                ),
            )
        except ConditionFailedError:
            raise ValueError(_DUPLICATE_MESSAGE_MESSAGE) from None

    async def list_page(
        self, session_id: str, *, limit: int, cursor: str | None
    ) -> Page[MessageRecord]:
        """Return the session's messages, newest first.

        :raises InvalidCursorError: If ``cursor`` was not issued for this list.
        """
        items, next_cursor = await query_page(
            self._client,
            self._table_name,
            partition_key=session_key(session_id),
            sort_prefix=MESSAGE_PREFIX,
            limit=limit,
            cursor=cursor,
        )
        return Page(items=tuple(_from_item(item) for item in items), next_cursor=next_cursor)

    async def delete_all(self, session_id: str) -> None:
        """Delete every message of the session, one batch of keys at a time.

        Each round reads the first remaining keys again, so a repeat after a partial failure
        continues where the failure stopped.

        :raises StorageUnavailableError: If DynamoDB keeps leaving items unprocessed.
        """
        query = prefix_query(
            self._table_name, partition_key=session_key(session_id), sort_prefix=MESSAGE_PREFIX
        )
        query["ProjectionExpression"] = _KEYS_ONLY
        query["ConsistentRead"] = True
        query["Limit"] = MAX_BATCH_WRITE_ITEMS
        while True:
            response = await run_dynamodb("Query", lambda: self._client.query(**query))
            if not response["Items"]:
                return
            await self._delete_batch([{"DeleteRequest": {"Key": key}} for key in response["Items"]])

    async def _delete_batch(self, requests: Sequence["WriteRequestUnionTypeDef"]) -> None:
        """Delete up to 25 items, retrying the ones DynamoDB leaves unprocessed."""
        pending = requests
        for attempt in range(MAX_UNPROCESSED_RETRIES + 1):
            call = functools.partial(
                self._client.batch_write_item, RequestItems={self._table_name: pending}
            )
            response = await run_dynamodb("BatchWriteItem", call)
            pending = response.get("UnprocessedItems", {}).get(self._table_name, [])
            if not pending:
                return
            await anyio.sleep(UNPROCESSED_RETRY_BASE_SECONDS * 2**attempt)
        logger.warning("DynamoDB BatchWriteItem left %d items unprocessed", len(pending))
        raise storage_unavailable()
