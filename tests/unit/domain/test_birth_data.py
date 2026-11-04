# SPDX-License-Identifier: AGPL-3.0-or-later
# All birth data here is synthetic; none of it belongs to a real person.
from datetime import UTC, date, datetime, time, timedelta
from http import HTTPStatus
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import InvalidBirthDataError
from app.domain.birth_data import (
    EARLIEST_BIRTH_DATE,
    AmbiguousTimeChoice,
    BirthData,
    local_birth_to_utc,
    require_birth_not_in_future,
)

PLACE_ID = "1"
KYIV = ZoneInfo("Europe/Kyiv")
SYDNEY = ZoneInfo("Australia/Sydney")
LORD_HOWE = ZoneInfo("Australia/Lord_Howe")
# Kyiv moved clocks from 03:00 to 04:00 on 2021-03-28, and from 04:00 back to 03:00 on
# 2021-10-31.
KYIV_GAP_DATE = date(2021, 3, 28)
KYIV_OVERLAP_DATE = date(2021, 10, 31)
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
# Zones with DST, historical offset changes, half-hour and non-hour offsets, both hemispheres.
PROPERTY_ZONES = (
    "Europe/Kyiv",
    "Europe/London",
    "America/New_York",
    "America/Sao_Paulo",
    "Australia/Sydney",
    "Australia/Lord_Howe",
    "Asia/Kolkata",
    "Asia/Kathmandu",
    "Arctic/Longyearbyen",
    "Pacific/Apia",
)


def _birth(
    local_date: date, local_time: time, ambiguous_time: AmbiguousTimeChoice | None = None
) -> BirthData:
    return BirthData(
        local_date=local_date,
        local_time=local_time,
        place_id=PLACE_ID,
        ambiguous_time=ambiguous_time,
    )


def _utc(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


@pytest.mark.parametrize(
    ("zone", "local_date", "local_time", "expected"),
    [
        pytest.param(KYIV, date(2000, 6, 1), time(12, 0), _utc(2000, 6, 1, 9, 0), id="summer"),
        pytest.param(KYIV, date(2000, 1, 1), time(0, 0), _utc(1999, 12, 31, 22, 0), id="midnight"),
        pytest.param(KYIV, date(2000, 2, 29), time(10, 0), _utc(2000, 2, 29, 8, 0), id="leap-day"),
        pytest.param(
            KYIV, date(1910, 1, 1), time(12, 0), _utc(1910, 1, 1, 9, 57, 56), id="kyiv-mean-time"
        ),
        pytest.param(
            KYIV, date(1985, 7, 1), time(12, 0), _utc(1985, 7, 1, 8, 0), id="moscow-summer-time"
        ),
        pytest.param(
            ZoneInfo("Asia/Kolkata"),
            date(1990, 5, 17),
            time(14, 30),
            _utc(1990, 5, 17, 9, 0),
            id="half-hour-offset",
        ),
        pytest.param(
            ZoneInfo("Arctic/Longyearbyen"),
            date(2000, 6, 21),
            time(12, 0),
            _utc(2000, 6, 21, 10, 0),
            id="polar-latitude",
        ),
        pytest.param(
            KYIV, KYIV_GAP_DATE, time(2, 59), _utc(2021, 3, 28, 0, 59), id="minute-before-gap"
        ),
        pytest.param(KYIV, KYIV_GAP_DATE, time(4, 0), _utc(2021, 3, 28, 1, 0), id="end-of-gap"),
    ],
)
def test_local_birth_to_utc_uses_zone_history(
    zone: ZoneInfo, local_date: date, local_time: time, expected: datetime
) -> None:
    result = local_birth_to_utc(_birth(local_date, local_time), zone)

    assert result == expected
    assert result.tzinfo is UTC


@pytest.mark.parametrize(
    ("zone", "local_date", "local_time"),
    [
        pytest.param(KYIV, KYIV_GAP_DATE, time(3, 0), id="first-skipped-minute"),
        pytest.param(KYIV, KYIV_GAP_DATE, time(3, 30), id="kyiv-spring-forward"),
        pytest.param(LORD_HOWE, date(2021, 10, 3), time(2, 15), id="half-hour-gap"),
    ],
)
@pytest.mark.parametrize("choice", [None, *AmbiguousTimeChoice])
def test_local_birth_to_utc_rejects_nonexistent_time(
    zone: ZoneInfo, local_date: date, local_time: time, choice: AmbiguousTimeChoice | None
) -> None:
    with pytest.raises(InvalidBirthDataError, match="does not exist"):
        local_birth_to_utc(_birth(local_date, local_time, choice), zone)


@pytest.mark.parametrize(
    ("zone", "local_date", "local_time", "earlier", "later"),
    [
        pytest.param(
            KYIV,
            KYIV_OVERLAP_DATE,
            time(3, 30),
            _utc(2021, 10, 31, 0, 30),
            _utc(2021, 10, 31, 1, 30),
            id="kyiv-fall-back",
        ),
        pytest.param(
            SYDNEY,
            date(2021, 4, 4),
            time(2, 30),
            _utc(2021, 4, 3, 15, 30),
            _utc(2021, 4, 3, 16, 30),
            id="southern-hemisphere",
        ),
        pytest.param(
            LORD_HOWE,
            date(2021, 4, 4),
            time(1, 45),
            _utc(2021, 4, 3, 14, 45),
            _utc(2021, 4, 3, 15, 15),
            id="half-hour-overlap",
        ),
    ],
)
def test_local_birth_to_utc_resolves_ambiguous_time_by_choice(
    zone: ZoneInfo, local_date: date, local_time: time, earlier: datetime, later: datetime
) -> None:
    resolved = {
        choice: local_birth_to_utc(_birth(local_date, local_time, choice), zone)
        for choice in AmbiguousTimeChoice
    }

    assert resolved == {AmbiguousTimeChoice.EARLIER: earlier, AmbiguousTimeChoice.LATER: later}


def test_local_birth_to_utc_rejects_ambiguous_time_without_choice() -> None:
    with pytest.raises(InvalidBirthDataError, match="earlier' or 'later"):
        local_birth_to_utc(_birth(KYIV_OVERLAP_DATE, time(3, 30)), KYIV)


@pytest.mark.parametrize("choice", list(AmbiguousTimeChoice))
def test_local_birth_to_utc_ignores_choice_for_unambiguous_time(
    choice: AmbiguousTimeChoice,
) -> None:
    result = local_birth_to_utc(_birth(date(2000, 6, 1), time(12, 0), choice), KYIV)

    assert result == _utc(2000, 6, 1, 9, 0)


@pytest.mark.parametrize(
    "birth",
    [
        _birth(KYIV_GAP_DATE, time(3, 30)),
        _birth(KYIV_OVERLAP_DATE, time(3, 30)),
    ],
)
def test_local_birth_to_utc_error_message_omits_birth_data(birth: BirthData) -> None:
    with pytest.raises(InvalidBirthDataError) as caught:
        local_birth_to_utc(birth, KYIV)

    assert "2021" not in caught.value.message
    assert "03:30" not in caught.value.message
    assert "3:30" not in caught.value.message


def test_invalid_birth_data_error_maps_to_unprocessable_content() -> None:
    assert InvalidBirthDataError.code == "invalid_birth_data"
    assert InvalidBirthDataError.http_status is HTTPStatus.UNPROCESSABLE_CONTENT


@given(
    local_date=st.dates(min_value=EARLIEST_BIRTH_DATE, max_value=date(2099, 12, 31)),
    local_time=st.times().map(lambda value: value.replace(second=0, microsecond=0)),
    zone_name=st.sampled_from(PROPERTY_ZONES),
    choice=st.sampled_from(AmbiguousTimeChoice),
)
def test_local_birth_to_utc_round_trips_to_local_wall_clock(
    local_date: date, local_time: time, zone_name: str, choice: AmbiguousTimeChoice
) -> None:
    zone = ZoneInfo(zone_name)
    try:
        result = local_birth_to_utc(_birth(local_date, local_time, choice), zone)
    except InvalidBirthDataError:
        # Only times skipped by a forward jump fail once a choice is given; their wall time
        # never appears on the zone's clock.
        candidate = datetime.combine(local_date, local_time, tzinfo=zone)
        round_trip = candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        assert round_trip != datetime.combine(local_date, local_time)
        return

    local = result.astimezone(zone)
    assert (local.date(), local.time()) == (local_date, local_time)


def test_require_birth_not_in_future_accepts_past_and_present() -> None:
    require_birth_not_in_future(NOW - timedelta(minutes=1), now=NOW)
    require_birth_not_in_future(NOW, now=NOW)


def test_require_birth_not_in_future_rejects_future_instant() -> None:
    with pytest.raises(InvalidBirthDataError, match="in the future"):
        require_birth_not_in_future(NOW + timedelta(minutes=1), now=NOW)


def test_require_birth_not_in_future_compares_instants_not_dates() -> None:
    # 20:00 in Tokyo on the same calendar date is 11:00 UTC, before NOW (12:00 UTC).
    tokyo_evening = local_birth_to_utc(_birth(NOW.date(), time(20, 0)), ZoneInfo("Asia/Tokyo"))

    require_birth_not_in_future(tokyo_evening, now=NOW)


@pytest.mark.parametrize(
    ("birth_utc", "now"),
    [
        (NOW.replace(tzinfo=None), NOW),
        (NOW, NOW.replace(tzinfo=None)),
    ],
)
def test_require_birth_not_in_future_rejects_naive_datetimes(
    birth_utc: datetime, now: datetime
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        require_birth_not_in_future(birth_utc, now=now)
