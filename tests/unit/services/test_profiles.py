# SPDX-License-Identifier: AGPL-3.0-or-later
# All birth data here is synthetic; none of it belongs to a real person.
import dataclasses
from datetime import UTC, date, datetime, time, timedelta

import pytest
from service_fakes import FakeClock, InMemoryPersonRepository, InMemoryProfileRepository
from ulid import ULID

from app.core.errors import PersonNotFoundError
from app.domain.profile import AnswerDepth, Tradition
from app.repositories.records import BirthRecord, PersonRecord, ProfileRecord
from app.services.profiles import ProfileService

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
BOTH_TRADITIONS = frozenset({Tradition.JYOTISHA, Tradition.BUKVITSA})


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def profile_repository() -> InMemoryProfileRepository:
    return InMemoryProfileRepository()


@pytest.fixture
def person_repository() -> InMemoryPersonRepository:
    return InMemoryPersonRepository()


@pytest.fixture
def service(
    profile_repository: InMemoryProfileRepository,
    person_repository: InMemoryPersonRepository,
    clock: FakeClock,
) -> ProfileService:
    return ProfileService(profile_repository, person_repository, clock=clock)


async def _add_person(persons: InMemoryPersonRepository, *, user_id: str = "alice") -> str:
    """Store a person directly; its birth data does not matter to the profile."""
    person = PersonRecord(
        user_id=user_id,
        person_id=str(ULID()),
        label="Me",
        birth=BirthRecord(
            local_date=date(1990, 5, 17),
            local_time=time(14, 30),
            ambiguous_time=None,
            place_id="4",
            place_name="Kyiv",
            place_region=None,
            place_country="Ukraine",
            latitude=50.45,
            longitude=30.52,
            timezone="Europe/Kyiv",
            places_dataset_version="2000-01-01",
            instant_utc=datetime(1990, 5, 17, 10, 30, tzinfo=UTC),
        ),
        created_at=NOW,
        updated_at=NOW,
    )
    await persons.create(person)
    return person.person_id


async def _replace(
    service: ProfileService,
    *,
    traditions: frozenset[Tradition] = frozenset({Tradition.JYOTISHA}),
    owner_person_id: str | None = None,
) -> ProfileRecord:
    return await service.replace(
        "alice",
        locale="uk",
        traditions=traditions,
        answer_depth=AnswerDepth.DETAILED,
        owner_person_id=owner_person_id,
    )


async def test_get_returns_none_before_first_save(service: ProfileService) -> None:
    assert await service.get("alice") is None


async def test_get_keeps_link_to_existing_person(
    service: ProfileService, person_repository: InMemoryPersonRepository
) -> None:
    person_id = await _add_person(person_repository)
    await _replace(service, owner_person_id=person_id)

    profile = await service.get("alice")

    assert profile is not None
    assert profile.owner_person_id == person_id


async def test_get_reports_link_to_deleted_person_as_none(
    service: ProfileService,
    person_repository: InMemoryPersonRepository,
    profile_repository: InMemoryProfileRepository,
) -> None:
    person_id = await _add_person(person_repository)
    saved = await _replace(service, owner_person_id=person_id)
    await person_repository.delete("alice", person_id)

    profile = await service.get("alice")

    assert profile == dataclasses.replace(saved, owner_person_id=None)
    assert await profile_repository.get("alice") == saved


async def test_replace_stores_preferences(service: ProfileService) -> None:
    profile = await _replace(service, traditions=BOTH_TRADITIONS)

    assert await service.get("alice") == profile
    assert (profile.user_id, profile.locale, profile.traditions, profile.answer_depth) == (
        "alice",
        "uk",
        BOTH_TRADITIONS,
        AnswerDepth.DETAILED,
    )
    assert profile.owner_person_id is None
    assert profile.created_at == profile.updated_at == NOW


async def test_replace_links_own_person(
    service: ProfileService, person_repository: InMemoryPersonRepository
) -> None:
    person_id = await _add_person(person_repository)

    profile = await _replace(service, owner_person_id=person_id)

    assert profile.owner_person_id == person_id


async def test_replace_with_unknown_person_raises_and_saves_nothing(
    service: ProfileService,
) -> None:
    with pytest.raises(PersonNotFoundError):
        await _replace(service, owner_person_id=str(ULID()))

    assert await service.get("alice") is None


async def test_replace_with_other_users_person_raises(
    service: ProfileService, person_repository: InMemoryPersonRepository
) -> None:
    bobs_person_id = await _add_person(person_repository, user_id="bob")

    with pytest.raises(PersonNotFoundError):
        await _replace(service, owner_person_id=bobs_person_id)


async def test_replace_without_traditions_raises(service: ProfileService) -> None:
    with pytest.raises(ValueError, match="traditions"):
        await _replace(service, traditions=frozenset())


async def test_replace_existing_profile_keeps_creation_time(
    service: ProfileService, clock: FakeClock
) -> None:
    await _replace(service)
    clock.advance(timedelta(days=1))

    replaced = await _replace(service, traditions=BOTH_TRADITIONS)

    assert (replaced.created_at, replaced.updated_at) == (NOW, NOW + timedelta(days=1))
    assert await service.get("alice") == replaced


async def test_delete_removes_profile(service: ProfileService) -> None:
    await _replace(service)

    await service.delete("alice")

    assert await service.get("alice") is None
