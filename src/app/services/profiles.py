# SPDX-License-Identifier: AGPL-3.0-or-later
"""A user's profile: preferences and the link to the person who is the account owner."""

import dataclasses
from typing import Final

from app.core.clock import Clock, utc_now
from app.core.errors import PersonNotFoundError
from app.domain.profile import AnswerDepth, Tradition
from app.repositories.protocols import PersonRepository, ProfileRepository
from app.repositories.records import ProfileRecord

_OWNER_PERSON_NOT_FOUND_MESSAGE: Final = "owner_person_id must name one of your persons."
_NO_TRADITIONS_MESSAGE: Final = "traditions must not be empty"


class ProfileService:
    """Read and replace profiles."""

    def __init__(
        self,
        profiles: ProfileRepository,
        persons: PersonRepository,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._profiles = profiles
        self._persons = persons
        self._clock = clock

    async def get(self, user_id: str) -> ProfileRecord | None:
        """Return the user's profile, or ``None`` before the first save.

        An ``owner_person_id`` naming a person that no longer exists is returned as ``None``:
        a profile save that races with deleting that person can leave such a link behind.
        """
        profile = await self._profiles.get(user_id)
        if profile is None or profile.owner_person_id is None:
            return profile
        if await self._persons.get(user_id, profile.owner_person_id) is None:
            return dataclasses.replace(profile, owner_person_id=None)
        return profile

    async def replace(
        self,
        user_id: str,
        *,
        locale: str,
        traditions: frozenset[Tradition],
        answer_depth: AnswerDepth,
        owner_person_id: str | None,
    ) -> ProfileRecord:
        """Create or replace the user's profile, keeping the original creation time.

        :param locale: BCP 47 language tag, validated by the API schema.
        :param traditions: Knowledge systems the user is interested in.
        :param owner_person_id: The person who is the account owner, or ``None`` for none.
        :returns: The saved profile.
        :raises ValueError: If ``traditions`` is empty; the API schema rejects that first.
        :raises PersonNotFoundError: If ``owner_person_id`` names no person of the user.
        """
        if not traditions:
            raise ValueError(_NO_TRADITIONS_MESSAGE)
        if owner_person_id is not None:
            await self._require_person(user_id, owner_person_id)
        now = self._clock()
        existing = await self._profiles.get(user_id)
        profile = ProfileRecord(
            user_id=user_id,
            locale=locale,
            traditions=traditions,
            answer_depth=answer_depth,
            owner_person_id=owner_person_id,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        await self._profiles.put(profile)
        return profile

    async def delete(self, user_id: str) -> None:
        """Delete the user's profile; does nothing if there is none."""
        await self._profiles.delete(user_id)

    async def _require_person(self, user_id: str, person_id: str) -> None:
        if await self._persons.get(user_id, person_id) is None:
            raise PersonNotFoundError(_OWNER_PERSON_NOT_FOUND_MESSAGE)
