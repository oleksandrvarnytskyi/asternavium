# SPDX-License-Identifier: AGPL-3.0-or-later
# All birth data here is synthetic; none of it belongs to a real person.
from datetime import UTC, date, datetime, time, timedelta

import pytest
from service_fakes import FakeClock, InMemoryPersonRepository, InMemoryProfileRepository
from ulid import ULID

from app.core.errors import InvalidBirthDataError, PersonNotFoundError, PlaceNotFoundError
from app.domain.birth_data import AmbiguousTimeChoice, BirthData
from app.domain.profile import AnswerDepth, Tradition
from app.repositories.geonames import GeoNamesPlaceRepository
from app.repositories.records import BirthRecord, PersonRecord, ProfileRecord
from app.services.persons import PersonService

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
# Place IDs of the synthetic places in conftest.TEST_PLACE_RECORDS.
PARIS_FRANCE = "1"
PARIS_TEXAS = "2"
KYIV = "4"
UNKNOWN_PLACE = "999999"
BIRTH_IN_TEXAS = BirthData(
    local_date=date(1990, 5, 17), local_time=time(14, 30), place_id=PARIS_TEXAS
)
BIRTH_IN_KYIV = BirthData(local_date=date(1965, 3, 2), local_time=time(6, 15), place_id=KYIV)
# More than one page of delete_all, so it must loop.
MANY_PERSONS = 30


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def person_repository() -> InMemoryPersonRepository:
    return InMemoryPersonRepository()


@pytest.fixture
def profile_repository() -> InMemoryProfileRepository:
    return InMemoryProfileRepository()


@pytest.fixture
def service(
    person_repository: InMemoryPersonRepository,
    profile_repository: InMemoryProfileRepository,
    place_repository: GeoNamesPlaceRepository,
    clock: FakeClock,
) -> PersonService:
    return PersonService(person_repository, profile_repository, place_repository, clock=clock)


async def _create(
    service: PersonService, birth: BirthData = BIRTH_IN_TEXAS, *, user_id: str = "alice"
) -> PersonRecord:
    return await service.create(user_id, label="Me", birth=birth)


async def _save_profile(
    profiles: InMemoryProfileRepository, *, owner_person_id: str | None
) -> ProfileRecord:
    profile = ProfileRecord(
        user_id="alice",
        locale="uk",
        traditions=frozenset({Tradition.JYOTISHA}),
        answer_depth=AnswerDepth.SIMPLE,
        owner_person_id=owner_person_id,
        created_at=NOW,
        updated_at=NOW,
    )
    await profiles.put(profile)
    return profile


async def test_create_copies_place_and_computes_utc_instant(
    service: PersonService, place_repository: GeoNamesPlaceRepository
) -> None:
    person = await _create(service)

    assert person.birth == BirthRecord(
        local_date=date(1990, 5, 17),
        local_time=time(14, 30),
        ambiguous_time=None,
        place_id=PARIS_TEXAS,
        place_name="Paris",
        place_region="Texas",
        place_country="United States",
        latitude=33.66,
        longitude=-95.56,
        timezone="America/Chicago",
        places_dataset_version=place_repository.dataset_version,
        # Central Daylight Time, UTC-5.
        instant_utc=datetime(1990, 5, 17, 19, 30, tzinfo=UTC),
    )


async def test_create_stores_person_at_current_time(service: PersonService) -> None:
    person = await _create(service)

    assert await service.get("alice", person.person_id) == person
    assert (person.user_id, person.label) == ("alice", "Me")
    assert person.created_at == person.updated_at == NOW
    assert ULID.from_str(person.person_id).datetime == NOW


async def test_create_keeps_place_without_region(service: PersonService) -> None:
    person = await _create(service, BIRTH_IN_KYIV)

    assert (person.birth.place_region, person.birth.place_country) == (None, "Ukraine")


async def test_create_with_unknown_place_raises_and_saves_nothing(
    service: PersonService,
) -> None:
    birth = BirthData(local_date=date(1990, 5, 17), local_time=time(14, 30), place_id=UNKNOWN_PLACE)

    with pytest.raises(PlaceNotFoundError):
        await _create(service, birth)

    assert (await service.list_page("alice", limit=10, cursor=None)).items == ()


async def test_create_with_time_skipped_by_dst_raises(service: PersonService) -> None:
    # Clocks in France moved from 02:00 to 03:00 on 2021-03-28.
    birth = BirthData(local_date=date(2021, 3, 28), local_time=time(2, 30), place_id=PARIS_FRANCE)

    with pytest.raises(InvalidBirthDataError):
        await _create(service, birth)


async def test_create_with_ambiguous_time_uses_chosen_instant(service: PersonService) -> None:
    # Clocks in France moved from 03:00 back to 02:00 on 2021-10-31; "later" is CET, UTC+1.
    birth = BirthData(
        local_date=date(2021, 10, 31),
        local_time=time(2, 30),
        place_id=PARIS_FRANCE,
        ambiguous_time=AmbiguousTimeChoice.LATER,
    )

    person = await _create(service, birth)

    assert person.birth.ambiguous_time is AmbiguousTimeChoice.LATER
    assert person.birth.instant_utc == datetime(2021, 10, 31, 1, 30, tzinfo=UTC)


async def test_create_with_birth_in_future_raises(service: PersonService) -> None:
    # 23:00 in Kyiv (UTC+2 in November) is 21:00 UTC, after NOW.
    birth = BirthData(local_date=NOW.date(), local_time=time(23, 0), place_id=KYIV)

    with pytest.raises(InvalidBirthDataError):
        await _create(service, birth)


async def test_list_page_returns_own_persons_newest_first(
    service: PersonService, clock: FakeClock
) -> None:
    for label in ("First", "Second", "Third"):
        await service.create("alice", label=label, birth=BIRTH_IN_TEXAS)
        clock.advance(timedelta(minutes=1))
    await _create(service, user_id="bob")

    first = await service.list_page("alice", limit=2, cursor=None)
    second = await service.list_page("alice", limit=2, cursor=first.next_cursor)

    assert [person.label for person in first.items] == ["Third", "Second"]
    assert [person.label for person in second.items] == ["First"]
    assert second.next_cursor is None


async def test_get_other_users_person_raises_not_found(service: PersonService) -> None:
    person = await _create(service)

    with pytest.raises(PersonNotFoundError):
        await service.get("bob", person.person_id)


async def test_replace_updates_label_and_birth_and_keeps_creation_time(
    service: PersonService, clock: FakeClock
) -> None:
    person = await _create(service)
    clock.advance(timedelta(days=1))

    replaced = await service.replace("alice", person.person_id, label="Mum", birth=BIRTH_IN_KYIV)

    assert (replaced.person_id, replaced.label, replaced.birth.place_name) == (
        person.person_id,
        "Mum",
        "Kyiv",
    )
    assert (replaced.created_at, replaced.updated_at) == (NOW, NOW + timedelta(days=1))
    assert await service.get("alice", person.person_id) == replaced


async def test_replace_other_users_person_raises_not_found(service: PersonService) -> None:
    person = await _create(service)

    with pytest.raises(PersonNotFoundError):
        await service.replace("bob", person.person_id, label="Hijacked", birth=BIRTH_IN_KYIV)

    assert await service.get("alice", person.person_id) == person


async def test_replace_with_invalid_birth_keeps_person(service: PersonService) -> None:
    person = await _create(service)
    birth = BirthData(local_date=date(1990, 5, 17), local_time=time(14, 30), place_id=UNKNOWN_PLACE)

    with pytest.raises(PlaceNotFoundError):
        await service.replace("alice", person.person_id, label="Mum", birth=birth)

    assert await service.get("alice", person.person_id) == person


async def test_delete_removes_person(service: PersonService) -> None:
    person = await _create(service)

    await service.delete("alice", person.person_id)

    with pytest.raises(PersonNotFoundError):
        await service.get("alice", person.person_id)


async def test_delete_of_other_users_person_leaves_it(service: PersonService) -> None:
    person = await _create(service)

    await service.delete("bob", person.person_id)

    assert await service.get("alice", person.person_id) == person


async def test_delete_of_owner_person_clears_profile_link(
    service: PersonService, profile_repository: InMemoryProfileRepository, clock: FakeClock
) -> None:
    person = await _create(service)
    await _save_profile(profile_repository, owner_person_id=person.person_id)
    clock.advance(timedelta(hours=1))

    await service.delete("alice", person.person_id)

    profile = await profile_repository.get("alice")
    assert profile is not None
    assert (profile.owner_person_id, profile.updated_at) == (None, NOW + timedelta(hours=1))


async def test_delete_of_other_person_keeps_profile_link(
    service: PersonService, profile_repository: InMemoryProfileRepository
) -> None:
    owner = await _create(service)
    mum = await service.create("alice", label="Mum", birth=BIRTH_IN_KYIV)
    profile = await _save_profile(profile_repository, owner_person_id=owner.person_id)

    await service.delete("alice", mum.person_id)

    assert await profile_repository.get("alice") == profile


async def test_delete_retry_clears_link_left_by_partial_failure(
    service: PersonService,
    person_repository: InMemoryPersonRepository,
    profile_repository: InMemoryProfileRepository,
) -> None:
    person = await _create(service)
    await _save_profile(profile_repository, owner_person_id=person.person_id)
    # A first attempt deleted the person, then failed before clearing the link.
    await person_repository.delete("alice", person.person_id)

    await service.delete("alice", person.person_id)

    profile = await profile_repository.get("alice")
    assert profile is not None
    assert profile.owner_person_id is None


async def test_delete_all_removes_every_person_of_the_user(service: PersonService) -> None:
    for _ in range(MANY_PERSONS):
        await _create(service)
    bobs = await _create(service, user_id="bob")

    await service.delete_all("alice")

    assert (await service.list_page("alice", limit=50, cursor=None)).items == ()
    assert await service.get("bob", bobs.person_id) == bobs
