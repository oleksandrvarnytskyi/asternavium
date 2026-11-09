# SPDX-License-Identifier: AGPL-3.0-or-later
"""Chat sessions in the DynamoDB app table."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.core.errors import SessionNotFoundError
from app.domain.chat import ChatModule
from app.repositories.app_table import PARTITION_KEY, SORT_KEY
from app.repositories.dynamodb_support import (
    ConditionFailedError,
    Item,
    key_item,
    number_value,
    query_page,
    read_int,
    read_string,
    read_timestamp,
    run_dynamodb,
    string_value,
    timestamp_value,
)
from app.repositories.keys import SESSION_PREFIX, USER_PREFIX, id_from_key, session_key, user_key
from app.repositories.records import Page, SessionRecord

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient

_SESSION_NOT_FOUND_MESSAGE: Final = "The session does not exist."
_DUPLICATE_SESSION_MESSAGE: Final = "A session with this ID already exists."
_ITEM_EXISTS: Final = "attribute_exists(#pk)"
_ITEM_MISSING: Final = "attribute_not_exists(#pk)"


class _Attribute(StrEnum):
    """Attribute names of a session item besides its keys."""

    TITLE = "title"
    MODULE = "module"
    MESSAGE_COUNT = "message_count"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


def _to_item(session: SessionRecord) -> Item:
    return key_item(user_key(session.user_id), session_key(session.session_id)) | {
        _Attribute.TITLE: string_value(session.title),
        _Attribute.MODULE: string_value(session.module),
        _Attribute.MESSAGE_COUNT: number_value(session.message_count),
        _Attribute.CREATED_AT: timestamp_value(session.created_at),
        _Attribute.UPDATED_AT: timestamp_value(session.updated_at),
    }


def _from_item(item: Item) -> SessionRecord:
    return SessionRecord(
        user_id=id_from_key(read_string(item, PARTITION_KEY), USER_PREFIX),
        session_id=id_from_key(read_string(item, SORT_KEY), SESSION_PREFIX),
        title=read_string(item, _Attribute.TITLE),
        module=ChatModule(read_string(item, _Attribute.MODULE)),
        message_count=read_int(item, _Attribute.MESSAGE_COUNT),
        created_at=read_timestamp(item, _Attribute.CREATED_AT),
        updated_at=read_timestamp(item, _Attribute.UPDATED_AT),
    )


class DynamoDBSessionRepository:
    """:class:`~app.repositories.protocols.SessionRepository` on the app table.

    Sessions live under their owner's partition, so a session ID of another user is simply
    not found.
    """

    def __init__(self, client: "DynamoDBClient", table_name: str) -> None:
        self._client = client
        self._table_name = table_name

    async def create(self, session: SessionRecord) -> None:
        """Store a new session.

        :raises ValueError: If a session with this ID already exists for the user.
        """
        item = _to_item(session)
        try:
            await run_dynamodb(
                "PutItem",
                lambda: self._client.put_item(
                    TableName=self._table_name,
                    Item=item,
                    ConditionExpression=_ITEM_MISSING,
                    ExpressionAttributeNames={"#pk": PARTITION_KEY},
                ),
            )
        except ConditionFailedError:
            raise ValueError(_DUPLICATE_SESSION_MESSAGE) from None

    async def get(self, user_id: str, session_id: str) -> SessionRecord | None:
        """Return the session, or ``None`` if the user has no session with this ID."""
        key = key_item(user_key(user_id), session_key(session_id))
        response = await run_dynamodb(
            "GetItem",
            lambda: self._client.get_item(TableName=self._table_name, Key=key, ConsistentRead=True),
        )
        item = response.get("Item")
        return _from_item(item) if item else None

    async def list_page(
        self, user_id: str, *, limit: int, cursor: str | None
    ) -> Page[SessionRecord]:
        """Return the user's sessions, newest first.

        :raises InvalidCursorError: If ``cursor`` was not issued for this list.
        """
        items, next_cursor = await query_page(
            self._client,
            self._table_name,
            partition_key=user_key(user_id),
            sort_prefix=SESSION_PREFIX,
            limit=limit,
            cursor=cursor,
        )
        return Page(items=tuple(_from_item(item) for item in items), next_cursor=next_cursor)

    async def rename(
        self, user_id: str, session_id: str, *, title: str, updated_at: datetime
    ) -> SessionRecord:
        """Set a session's title.

        :raises SessionNotFoundError: If the user has no session with this ID.
        """
        key = key_item(user_key(user_id), session_key(session_id))
        try:
            response = await run_dynamodb(
                "UpdateItem",
                lambda: self._client.update_item(
                    TableName=self._table_name,
                    Key=key,
                    UpdateExpression="SET #title = :title, #updated_at = :updated_at",
                    ConditionExpression=_ITEM_EXISTS,
                    ExpressionAttributeNames={
                        "#pk": PARTITION_KEY,
                        "#title": _Attribute.TITLE,
                        "#updated_at": _Attribute.UPDATED_AT,
                    },
                    ExpressionAttributeValues={
                        ":title": string_value(title),
                        ":updated_at": timestamp_value(updated_at),
                    },
                    ReturnValues="ALL_NEW",
                ),
            )
        except ConditionFailedError:
            raise SessionNotFoundError(_SESSION_NOT_FOUND_MESSAGE) from None
        return _from_item(response["Attributes"])

    async def delete(self, user_id: str, session_id: str) -> None:
        """Delete the session record, not its messages; does nothing if it does not exist."""
        key = key_item(user_key(user_id), session_key(session_id))
        await run_dynamodb(
            "DeleteItem", lambda: self._client.delete_item(TableName=self._table_name, Key=key)
        )
