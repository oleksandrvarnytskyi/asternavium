# SPDX-License-Identifier: AGPL-3.0-or-later
import dataclasses
from datetime import UTC, datetime

import pytest
from ulid import ULID

from app.domain.profile import AnswerDepth, Tradition
from app.repositories.dynamodb_profiles import DynamoDBProfileRepository
from app.repositories.records import ProfileRecord

pytestmark = pytest.mark.anyio

CREATED = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
UPDATED = datetime(2026, 11, 5, 9, 30, tzinfo=UTC)


def _profile(user_id: str = "alice", **changes: object) -> ProfileRecord:
    profile = ProfileRecord(
        user_id=user_id,
        locale="uk",
        traditions=frozenset({Tradition.JYOTISHA}),
        answer_depth=AnswerDepth.SIMPLE,
        owner_person_id=None,
        created_at=CREATED,
        updated_at=CREATED,
    )
    return dataclasses.replace(profile, **changes)  # type: ignore[arg-type]  # test-only overrides


async def test_get_returns_none_without_profile(profiles: DynamoDBProfileRepository) -> None:
    assert await profiles.get("alice") is None


async def test_put_then_get_round_trips_every_field(profiles: DynamoDBProfileRepository) -> None:
    profile = _profile()

    await profiles.put(profile)

    assert await profiles.get("alice") == profile


async def test_put_round_trips_several_traditions(profiles: DynamoDBProfileRepository) -> None:
    profile = _profile(traditions=frozenset({Tradition.JYOTISHA, Tradition.BUKVITSA}))

    await profiles.put(profile)

    assert await profiles.get("alice") == profile


async def test_put_round_trips_owner_person_id(profiles: DynamoDBProfileRepository) -> None:
    profile = _profile(owner_person_id=str(ULID()))

    await profiles.put(profile)

    assert await profiles.get("alice") == profile


async def test_put_replaces_existing_profile(profiles: DynamoDBProfileRepository) -> None:
    await profiles.put(_profile(owner_person_id=str(ULID())))
    replacement = _profile(
        traditions=frozenset({Tradition.BUKVITSA}),
        answer_depth=AnswerDepth.TECHNICAL,
        updated_at=UPDATED,
    )

    await profiles.put(replacement)

    assert await profiles.get("alice") == replacement


async def test_profiles_of_different_users_are_separate(
    profiles: DynamoDBProfileRepository,
) -> None:
    await profiles.put(_profile("alice"))

    assert await profiles.get("bob") is None


async def test_delete_removes_profile(profiles: DynamoDBProfileRepository) -> None:
    await profiles.put(_profile("alice"))
    await profiles.put(_profile("bob"))

    await profiles.delete("alice")

    assert await profiles.get("alice") is None
    assert await profiles.get("bob") is not None


async def test_delete_without_profile_succeeds(profiles: DynamoDBProfileRepository) -> None:
    await profiles.delete("alice")

    assert await profiles.get("alice") is None
