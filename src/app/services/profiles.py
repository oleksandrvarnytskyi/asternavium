# SPDX-License-Identifier: AGPL-3.0-or-later
"""A user's profile: birth data resolved against the place data, plus preferences.

Birth data is personal data: nothing here logs it, and error messages never contain it.
"""

from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from app.core.clock import Clock, utc_now
from app.core.errors import PlaceNotFoundError
from app.domain.birth_data import BirthData, local_birth_to_utc, require_birth_not_in_future
from app.domain.profile import AnswerDepth, Tradition
from app.repositories.places import PlaceRepository
from app.repositories.protocols import ProfileRepository
from app.repositories.records import BirthRecord, ProfileRecord

_PLACE_NOT_FOUND_MESSAGE: Final = "Unknown birth place. Choose a place from GET /v1/places."


class ProfileService:
    """Read and replace profiles."""

    def __init__(
        self,
        profiles: ProfileRepository,
        places: PlaceRepository,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._profiles = profiles
        self._places = places
        self._clock = clock

    async def get(self, user_id: str) -> ProfileRecord | None:
        """Return the user's profile, or ``None`` before the first save."""
        return await self._profiles.get(user_id)

    async def replace(
        self,
        user_id: str,
        *,
        birth: BirthData,
        locale: str,
        tradition: Tradition,
        answer_depth: AnswerDepth,
    ) -> ProfileRecord:
        """Create or replace the user's profile.

        Copies the place's name, region, country, coordinates and time zone into the profile,
        so a later refresh of the place data never changes it. Keeps the original creation
        time.

        :param locale: BCP 47 language tag, validated by the API schema.
        :returns: The saved profile.
        :raises PlaceNotFoundError: If ``birth.place_id`` is not in the place data.
        :raises InvalidBirthDataError: If the local birth time does not exist or is ambiguous
            at the place, or the birth is in the future.
        """
        now = self._clock()
        birth_record = self._resolve_birth(birth, now=now)
        existing = await self._profiles.get(user_id)
        profile = ProfileRecord(
            user_id=user_id,
            birth=birth_record,
            locale=locale,
            tradition=tradition,
            answer_depth=answer_depth,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        await self._profiles.put(profile)
        return profile

    async def delete(self, user_id: str) -> None:
        """Delete the user's profile; does nothing if there is none."""
        await self._profiles.delete(user_id)

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
