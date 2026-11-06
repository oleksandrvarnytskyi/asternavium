# SPDX-License-Identifier: AGPL-3.0-or-later
# All birth data here is synthetic; none of it belongs to a real person.
from datetime import UTC, date, datetime, time, timedelta

import pytest
from service_fakes import FakeClock, InMemoryProfileRepository

from app.core.errors import InvalidBirthDataError, PlaceNotFoundError
from app.domain.birth_data import AmbiguousTimeChoice, BirthData
from app.domain.profile import AnswerDepth, Tradition
from app.repositories.geonames import GeoNamesPlaceRepository
from app.repositories.records import BirthRecord, ProfileRecord
from app.services.profiles import ProfileService

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


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def profile_repository() -> InMemoryProfileRepository:
    return InMemoryProfileRepository()


@pytest.fixture
def service(
    profile_repository: InMemoryProfileRepository,
    place_repository: GeoNamesPlaceRepository,
    clock: FakeClock,
) -> ProfileService:
    return ProfileService(profile_repository, place_repository, clock=clock)


async def _replace(
    service: ProfileService,
    birth: BirthData = BIRTH_IN_TEXAS,
    *,
    tradition: Tradition = Tradition.JYOTISHA,
) -> ProfileRecord:
    return await service.replace(
        "alice",
        birth=birth,
        locale="uk",
        tradition=tradition,
        answer_depth=AnswerDepth.ESSENTIALS,
    )


async def test_get_returns_none_before_first_save(service: ProfileService) -> None:
    assert await service.get("alice") is None


async def test_replace_copies_place_and_computes_utc_instant(
    service: ProfileService, place_repository: GeoNamesPlaceRepository
) -> None:
    profile = await _replace(service)

    assert profile.birth == BirthRecord(
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


async def test_replace_stores_profile_with_preferences(service: ProfileService) -> None:
    profile = await _replace(service, tradition=Tradition.BUKVITSA)

    assert await service.get("alice") == profile
    assert (profile.user_id, profile.locale, profile.tradition, profile.answer_depth) == (
        "alice",
        "uk",
        Tradition.BUKVITSA,
        AnswerDepth.ESSENTIALS,
    )
    assert profile.created_at == profile.updated_at == NOW


async def test_replace_keeps_place_without_region(service: ProfileService) -> None:
    birth = BirthData(local_date=date(1990, 5, 17), local_time=time(14, 30), place_id=KYIV)

    profile = await _replace(service, birth)

    assert (profile.birth.place_region, profile.birth.place_country) == (None, "Ukraine")


async def test_replace_existing_profile_keeps_creation_time(
    service: ProfileService, clock: FakeClock
) -> None:
    await _replace(service)
    clock.advance(timedelta(days=1))

    replaced = await _replace(service, tradition=Tradition.BUKVITSA)

    assert (replaced.created_at, replaced.updated_at) == (NOW, NOW + timedelta(days=1))
    assert await service.get("alice") == replaced


async def test_replace_with_unknown_place_raises_and_saves_nothing(
    service: ProfileService,
) -> None:
    birth = BirthData(local_date=date(1990, 5, 17), local_time=time(14, 30), place_id=UNKNOWN_PLACE)

    with pytest.raises(PlaceNotFoundError):
        await _replace(service, birth)

    assert await service.get("alice") is None


async def test_replace_with_time_skipped_by_dst_raises(service: ProfileService) -> None:
    # Clocks in France moved from 02:00 to 03:00 on 2021-03-28.
    birth = BirthData(local_date=date(2021, 3, 28), local_time=time(2, 30), place_id=PARIS_FRANCE)

    with pytest.raises(InvalidBirthDataError):
        await _replace(service, birth)

    assert await service.get("alice") is None


async def test_replace_with_ambiguous_time_uses_chosen_instant(service: ProfileService) -> None:
    # Clocks in France moved from 03:00 back to 02:00 on 2021-10-31; "later" is CET, UTC+1.
    birth = BirthData(
        local_date=date(2021, 10, 31),
        local_time=time(2, 30),
        place_id=PARIS_FRANCE,
        ambiguous_time=AmbiguousTimeChoice.LATER,
    )

    profile = await _replace(service, birth)

    assert profile.birth.ambiguous_time is AmbiguousTimeChoice.LATER
    assert profile.birth.instant_utc == datetime(2021, 10, 31, 1, 30, tzinfo=UTC)


async def test_replace_with_birth_in_future_raises(service: ProfileService) -> None:
    # 23:00 in Kyiv (UTC+2 in November) is 21:00 UTC, after NOW.
    birth = BirthData(local_date=NOW.date(), local_time=time(23, 0), place_id=KYIV)

    with pytest.raises(InvalidBirthDataError):
        await _replace(service, birth)


async def test_delete_removes_profile(service: ProfileService) -> None:
    await _replace(service)

    await service.delete("alice")

    assert await service.get("alice") is None
