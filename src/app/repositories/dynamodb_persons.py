# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persons and their birth data in the DynamoDB app table."""

from datetime import date, time
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.core.errors import PersonNotFoundError
from app.domain.birth_data import AmbiguousTimeChoice
from app.repositories.app_table import PARTITION_KEY, SORT_KEY
from app.repositories.dynamodb_support import (
    ConditionFailedError,
    Item,
    key_item,
    number_value,
    query_page,
    read_float,
    read_optional_string,
    read_string,
    read_timestamp,
    run_dynamodb,
    string_value,
    timestamp_value,
)
from app.repositories.keys import PERSON_PREFIX, USER_PREFIX, id_from_key, person_key, user_key
from app.repositories.records import BirthRecord, Page, PersonRecord

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient

_TIME_PRECISION: Final = "minutes"
_PERSON_NOT_FOUND_MESSAGE: Final = "The person does not exist."
_DUPLICATE_PERSON_MESSAGE: Final = "A person with this ID already exists."
_ITEM_EXISTS: Final = "attribute_exists(#pk)"
_ITEM_MISSING: Final = "attribute_not_exists(#pk)"


class _Attribute(StrEnum):
    """Attribute names of a person item besides its keys."""

    LABEL = "label"
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
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


def _to_item(person: PersonRecord) -> Item:
    birth = person.birth
    item = key_item(user_key(person.user_id), person_key(person.person_id)) | {
        _Attribute.LABEL: string_value(person.label),
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
        _Attribute.CREATED_AT: timestamp_value(person.created_at),
        _Attribute.UPDATED_AT: timestamp_value(person.updated_at),
    }
    if birth.ambiguous_time is not None:
        item[_Attribute.BIRTH_AMBIGUOUS_TIME] = string_value(birth.ambiguous_time)
    if birth.place_region is not None:
        item[_Attribute.BIRTH_PLACE_REGION] = string_value(birth.place_region)
    return item


def _from_item(item: Item) -> PersonRecord:
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
    return PersonRecord(
        user_id=id_from_key(read_string(item, PARTITION_KEY), USER_PREFIX),
        person_id=id_from_key(read_string(item, SORT_KEY), PERSON_PREFIX),
        label=read_string(item, _Attribute.LABEL),
        birth=birth,
        created_at=read_timestamp(item, _Attribute.CREATED_AT),
        updated_at=read_timestamp(item, _Attribute.UPDATED_AT),
    )


class DynamoDBPersonRepository:
    """:class:`~app.repositories.protocols.PersonRepository` on the app table.

    Persons live under their owner's partition, so a person ID of another user is simply
    not found.
    """

    def __init__(self, client: "DynamoDBClient", table_name: str) -> None:
        self._client = client
        self._table_name = table_name

    async def create(self, person: PersonRecord) -> None:
        """Store a new person.

        :raises ValueError: If a person with this ID already exists for the user.
        """
        try:
            await self._put(person, condition=_ITEM_MISSING)
        except ConditionFailedError:
            raise ValueError(_DUPLICATE_PERSON_MESSAGE) from None

    async def get(self, user_id: str, person_id: str) -> PersonRecord | None:
        """Return the person, or ``None`` if the user has no person with this ID."""
        key = key_item(user_key(user_id), person_key(person_id))
        response = await run_dynamodb(
            "GetItem",
            lambda: self._client.get_item(TableName=self._table_name, Key=key, ConsistentRead=True),
        )
        item = response.get("Item")
        return None if item is None else _from_item(item)

    async def list_page(
        self, user_id: str, *, limit: int, cursor: str | None
    ) -> Page[PersonRecord]:
        """Return the user's persons, newest first.

        :raises InvalidCursorError: If ``cursor`` was not issued for this list.
        """
        items, next_cursor = await query_page(
            self._client,
            self._table_name,
            partition_key=user_key(user_id),
            sort_prefix=PERSON_PREFIX,
            limit=limit,
            cursor=cursor,
        )
        return Page(items=tuple(_from_item(item) for item in items), next_cursor=next_cursor)

    async def replace(self, person: PersonRecord) -> None:
        """Overwrite an existing person.

        :raises PersonNotFoundError: If the user has no person with this ID.
        """
        try:
            await self._put(person, condition=_ITEM_EXISTS)
        except ConditionFailedError:
            raise PersonNotFoundError(_PERSON_NOT_FOUND_MESSAGE) from None

    async def delete(self, user_id: str, person_id: str) -> None:
        """Delete the person; does nothing if it does not exist."""
        key = key_item(user_key(user_id), person_key(person_id))
        await run_dynamodb(
            "DeleteItem", lambda: self._client.delete_item(TableName=self._table_name, Key=key)
        )

    async def _put(self, person: PersonRecord, *, condition: str) -> None:
        """Write the person's item if ``condition`` on its partition key holds."""
        item = _to_item(person)
        await run_dynamodb(
            "PutItem",
            lambda: self._client.put_item(
                TableName=self._table_name,
                Item=item,
                ConditionExpression=condition,
                ExpressionAttributeNames={"#pk": PARTITION_KEY},
            ),
        )
