# SPDX-License-Identifier: AGPL-3.0-or-later
"""Profiles in the DynamoDB app table."""

from enum import StrEnum
from typing import TYPE_CHECKING

from app.domain.profile import AnswerDepth, Tradition
from app.repositories.app_table import PARTITION_KEY
from app.repositories.dynamodb_support import (
    Item,
    key_item,
    read_optional_string,
    read_string,
    read_string_set,
    read_timestamp,
    run_dynamodb,
    string_set_value,
    string_value,
    timestamp_value,
)
from app.repositories.keys import PROFILE_SORT_KEY, USER_PREFIX, id_from_key, user_key
from app.repositories.records import ProfileRecord

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient


class _Attribute(StrEnum):
    """Attribute names of a profile item besides its keys."""

    LOCALE = "locale"
    TRADITIONS = "traditions"
    ANSWER_DEPTH = "answer_depth"
    OWNER_PERSON_ID = "owner_person_id"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


def _to_item(profile: ProfileRecord) -> Item:
    item = key_item(user_key(profile.user_id), PROFILE_SORT_KEY) | {
        _Attribute.LOCALE: string_value(profile.locale),
        _Attribute.TRADITIONS: string_set_value(profile.traditions),
        _Attribute.ANSWER_DEPTH: string_value(profile.answer_depth),
        _Attribute.CREATED_AT: timestamp_value(profile.created_at),
        _Attribute.UPDATED_AT: timestamp_value(profile.updated_at),
    }
    if profile.owner_person_id is not None:
        item[_Attribute.OWNER_PERSON_ID] = string_value(profile.owner_person_id)
    return item


def _from_item(item: Item) -> ProfileRecord:
    return ProfileRecord(
        user_id=id_from_key(read_string(item, PARTITION_KEY), USER_PREFIX),
        locale=read_string(item, _Attribute.LOCALE),
        traditions=frozenset(
            Tradition(value) for value in read_string_set(item, _Attribute.TRADITIONS)
        ),
        answer_depth=AnswerDepth(read_string(item, _Attribute.ANSWER_DEPTH)),
        owner_person_id=read_optional_string(item, _Attribute.OWNER_PERSON_ID),
        created_at=read_timestamp(item, _Attribute.CREATED_AT),
        updated_at=read_timestamp(item, _Attribute.UPDATED_AT),
    )


class DynamoDBProfileRepository:
    """:class:`~app.repositories.protocols.ProfileRepository` on the app table."""

    def __init__(self, client: "DynamoDBClient", table_name: str) -> None:
        self._client = client
        self._table_name = table_name

    async def get(self, user_id: str) -> ProfileRecord | None:
        """Return the user's profile, or ``None`` if none was saved."""
        key = key_item(user_key(user_id), PROFILE_SORT_KEY)
        response = await run_dynamodb(
            "GetItem",
            lambda: self._client.get_item(TableName=self._table_name, Key=key, ConsistentRead=True),
        )
        item = response.get("Item")
        return _from_item(item) if item else None

    async def put(self, profile: ProfileRecord) -> None:
        """Create or replace the user's profile."""
        item = _to_item(profile)
        await run_dynamodb(
            "PutItem", lambda: self._client.put_item(TableName=self._table_name, Item=item)
        )

    async def delete(self, user_id: str) -> None:
        """Delete the user's profile; does nothing if there is none."""
        key = key_item(user_key(user_id), PROFILE_SORT_KEY)
        await run_dynamodb(
            "DeleteItem", lambda: self._client.delete_item(TableName=self._table_name, Key=key)
        )
