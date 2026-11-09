# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persons a user makes charts for, with their birth data resolved against the place data.

Birth data is personal data: nothing here logs it, and error messages never contain it.
"""

import dataclasses
from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from ulid import ULID

from app.core.clock import Clock, utc_now
from app.core.errors import PersonNotFoundError, PlaceNotFoundError
from app.domain.birth_data import BirthData, local_birth_to_utc, require_birth_not_in_future
from app.repositories.places import PlaceRepository
from app.repositories.protocols import PersonRepository, ProfileRepository
from app.repositories.records import BirthRecord, Page, PersonRecord

_PERSON_NOT_FOUND_MESSAGE: Final = "Person not found."
_PLACE_NOT_FOUND_MESSAGE: Final = "Unknown birth place. Choose a place from GET /v1/places."
# delete_all removes each page it reads, so it re-reads the first page until it is empty.
_DELETE_ALL_PAGE_SIZE: Final = 25


class PersonService:
    """Add, read, replace and delete a user's persons.

    Every method takes the caller's user ID; a person of another user is reported exactly
    like a missing one.
    """

    def __init__(
        self,
        persons: PersonRepository,
        profiles: ProfileRepository,
        places: PlaceRepository,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._persons = persons
        self._profiles = profiles
        self._places = places
        self._clock = clock

    async def create(self, user_id: str, *, label: str, birth: BirthData) -> PersonRecord:
        """Add a person.

        :param label: The user's name for the person; length is limited by the API schema.
        :returns: The new person; its ULID encodes the creation time.
        :raises PlaceNotFoundError: If ``birth.place_id`` is not in the place data.
        :raises InvalidBirthDataError: If the local birth time does not exist or is ambiguous
            at the place, or the birth is in the future.
        """
        now = self._clock()
        person = PersonRecord(
            user_id=user_id,
            person_id=str(ULID.from_datetime(now)),
            label=label,
            birth=self._resolve_birth(birth, now=now),
            created_at=now,
            updated_at=now,
        )
        await self._persons.create(person)
        return person

    async def list_page(
        self, user_id: str, *, limit: int, cursor: str | None
    ) -> Page[PersonRecord]:
        """Return the user's persons, newest first.

        :param limit: Maximum persons on the page; positive.
        :param cursor: ``next_cursor`` of the previous page, or ``None`` for the first page.
        :raises InvalidCursorError: If ``cursor`` was not issued for this list.
        """
        return await self._persons.list_page(user_id, limit=limit, cursor=cursor)

    async def get(self, user_id: str, person_id: str) -> PersonRecord:
        """Return one of the user's persons.

        :raises PersonNotFoundError: If the user has no person with this ID.
        """
        person = await self._persons.get(user_id, person_id)
        if person is None:
            raise PersonNotFoundError(_PERSON_NOT_FOUND_MESSAGE)
        return person

    async def replace(
        self, user_id: str, person_id: str, *, label: str, birth: BirthData
    ) -> PersonRecord:
        """Replace a person's label and birth data, keeping the creation time.

        :returns: The saved person.
        :raises PersonNotFoundError: If the user has no person with this ID.
        :raises PlaceNotFoundError: If ``birth.place_id`` is not in the place data.
        :raises InvalidBirthDataError: If the local birth time does not exist or is ambiguous
            at the place, or the birth is in the future.
        """
        existing = await self.get(user_id, person_id)
        now = self._clock()
        person = dataclasses.replace(
            existing, label=label, birth=self._resolve_birth(birth, now=now), updated_at=now
        )
        await self._persons.replace(person)
        return person

    async def delete(self, user_id: str, person_id: str) -> None:
        """Delete a person; does nothing if the user has no such person.

        If the profile names the person as the user, that link is cleared after the delete,
        so a retry after a partial failure still clears it.
        """
        await self._persons.delete(user_id, person_id)
        profile = await self._profiles.get(user_id)
        if profile is not None and profile.owner_person_id == person_id:
            await self._profiles.put(
                dataclasses.replace(profile, owner_person_id=None, updated_at=self._clock())
            )

    async def delete_all(self, user_id: str) -> None:
        """Delete every person of the user; safe to repeat.

        Leaves the profile's ``owner_person_id`` alone; account deletion removes the profile.
        """
        while True:
            page = await self._persons.list_page(user_id, limit=_DELETE_ALL_PAGE_SIZE, cursor=None)
            if not page.items:
                return
            for person in page.items:
                await self._persons.delete(user_id, person.person_id)

    def _resolve_birth(self, birth: BirthData, *, now: datetime) -> BirthRecord:
        """Look the place up and compute the UTC birth instant."""
        place = self._places.get(birth.place_id)
        if place is None:
            raise PlaceNotFoundError(_PLACE_NOT_FOUND_MESSAGE)
        instant_utc = local_birth_to_utc(birth, ZoneInfo(place.timezone))
        require_birth_not_in_future(instant_utc, now=now)
        return BirthRecord(
            local_date=birth.local_date,
            local_time=birth.local_time,
            ambiguous_time=birth.ambiguous_time,
            place_id=place.place_id,
            place_name=place.name,
            place_region=place.region,
            place_country=place.country,
            latitude=place.latitude,
            longitude=place.longitude,
            timezone=place.timezone,
            places_dataset_version=self._places.dataset_version,
            instant_utc=instant_utc,
        )
