# SPDX-License-Identifier: AGPL-3.0-or-later
"""Profiles in the DynamoDB app table."""

from datetime import date, time
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.domain.birth_data import AmbiguousTimeChoice
from app.domain.profile import AnswerDepth, Tradition
from app.repositories.app_table import PARTITION_KEY
from app.repositories.dynamodb_support import (
    Item,
    key_item,
    number_value,
    read_float,
    read_optional_string,
    read_string,
    read_timestamp,
    run_dynamodb,
    string_value,
    timestamp_value,
)
from app.repositories.keys import PROFILE_SORT_KEY, USER_PREFIX, id_from_key, user_key
from app.repositories.records import BirthRecord, ProfileRecord

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient

_TIME_PRECISION: Final = "minutes"


class _Attribute(StrEnum):
    """Attribute names of a profile item besides its keys."""

    BIRTH_LOCAL_DATE = "birth_local_date"
    BIRTH_LOCAL_TIME = "birth_local_time"
    BIRTH_AMBIGUOUS_TIME = "birth_ambiguous_time"
    BIRTH_PLACE_ID = "birth_place_id"
    BIRTH_PLACE_NAME = "birth_place_name"
    BIRTH_PLACE_REGION = "birth_place_region"
    BIRTH_PLACE_COUNTRY = "birth_place_country"
    BIRTH_LATITUDE = "birth_latitude"
    BIRTH_LONGITUDE = "birth_longitude"
    BIRTH_TIMEZONE = "birth_timezone"
    PLACES_DATASET_VERSION = "places_dataset_version"
    BIRTH_INSTANT_UTC = "birth_instant_utc"
    LOCALE = "locale"
    TRADITION = "tradition"
    ANSWER_DEPTH = "answer_depth"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


def _to_item(profile: ProfileRecord) -> Item:
    birth = profile.birth
    item = key_item(user_key(profile.user_id), PROFILE_SORT_KEY) | {
        _Attribute.BIRTH_LOCAL_DATE: string_value(birth.local_date.isoformat()),
        _Attribute.BIRTH_LOCAL_TIME: string_value(
            birth.local_time.isoformat(timespec=_TIME_PRECISION)
        ),
        _Attribute.BIRTH_PLACE_ID: string_value(birth.place_id),
        _Attribute.BIRTH_PLACE_NAME: string_value(birth.place_name),
        _Attribute.BIRTH_PLACE_COUNTRY: string_value(birth.place_country),
        _Attribute.BIRTH_LATITUDE: number_value(birth.latitude),
        _Attribute.BIRTH_LONGITUDE: number_value(birth.longitude),
        _Attribute.BIRTH_TIMEZONE: string_value(birth.timezone),
        _Attribute.PLACES_DATASET_VERSION: string_value(birth.places_dataset_version),
        _Attribute.BIRTH_INSTANT_UTC: timestamp_value(birth.instant_utc),
        _Attribute.LOCALE: string_value(profile.locale),
        _Attribute.TRADITION: string_value(profile.tradition),
        _Attribute.ANSWER_DEPTH: string_value(profile.answer_depth),
        _Attribute.CREATED_AT: timestamp_value(profile.created_at),
        _Attribute.UPDATED_AT: timestamp_value(profile.updated_at),
    }
    if birth.ambiguous_time is not None:
        item[_Attribute.BIRTH_AMBIGUOUS_TIME] = string_value(birth.ambiguous_time)
    if birth.place_region is not None:
        item[_Attribute.BIRTH_PLACE_REGION] = string_value(birth.place_region)
    return item


def _from_item(item: Item) -> ProfileRecord:
    ambiguous_time = read_optional_string(item, _Attribute.BIRTH_AMBIGUOUS_TIME)
    birth = BirthRecord(
        local_date=date.fromisoformat(read_string(item, _Attribute.BIRTH_LOCAL_DATE)),
        local_time=time.fromisoformat(read_string(item, _Attribute.BIRTH_LOCAL_TIME)),
        ambiguous_time=None if ambiguous_time is None else AmbiguousTimeChoice(ambiguous_time),
        place_id=read_string(item, _Attribute.BIRTH_PLACE_ID),
        place_name=read_string(item, _Attribute.BIRTH_PLACE_NAME),
        place_region=read_optional_string(item, _Attribute.BIRTH_PLACE_REGION),
        place_country=read_string(item, _Attribute.BIRTH_PLACE_COUNTRY),
        latitude=read_float(item, _Attribute.BIRTH_LATITUDE),
        longitude=read_float(item, _Attribute.BIRTH_LONGITUDE),
        timezone=read_string(item, _Attribute.BIRTH_TIMEZONE),
        places_dataset_version=read_string(item, _Attribute.PLACES_DATASET_VERSION),
        instant_utc=read_timestamp(item, _Attribute.BIRTH_INSTANT_UTC),
    )
    return ProfileRecord(
        user_id=id_from_key(read_string(item, PARTITION_KEY), USER_PREFIX),
        birth=birth,
        locale=read_string(item, _Attribute.LOCALE),
        tradition=Tradition(read_string(item, _Attribute.TRADITION)),
        answer_depth=AnswerDepth(read_string(item, _Attribute.ANSWER_DEPTH)),
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
        return None if item is None else _from_item(item)

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
