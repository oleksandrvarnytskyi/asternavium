# SPDX-License-Identifier: AGPL-3.0-or-later
"""Birth data value type and conversion of the local birth moment to UTC.

Birth data is personal data: nothing here logs it, and error messages never contain it.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import StrEnum
from typing import Final
from zoneinfo import ZoneInfo

from app.core.errors import InvalidBirthDataError

# Earliest accepted birthdate: users are living people, and time zone history before 1900 is
# sparse (mostly local mean time) in the IANA database.
EARLIEST_BIRTH_DATE: Final = date(1900, 1, 1)
_FUTURE_BIRTH_MESSAGE: Final = "The birth date and time are in the future. Check the birth data."
_NONEXISTENT_TIME_MESSAGE: Final = (
    "The birth time does not exist at the birth place: clocks were moved forward then. "
    "Check the birth time."
)
_AMBIGUOUS_TIME_MESSAGE: Final = (
    "The birth time occurred twice at the birth place because clocks were moved back; "
    "set ambiguous_time to 'earlier' or 'later'."
)


class AmbiguousTimeChoice(StrEnum):
    """Which instant a local time means when it occurs twice, as when clocks are set back."""

    EARLIER = "earlier"
    LATER = "later"


@dataclass(frozen=True, slots=True)
class BirthData:
    """Birth moment as the user gave it, in the birth place's local time.

    :ivar local_date: Calendar date at the birth place (proleptic Gregorian).
    :ivar local_time: Wall-clock time at the birth place, to the minute and without a zone;
        the zone comes from the place.
    :ivar place_id: ID of the birth place from the place repository.
    :ivar ambiguous_time: Which instant to use if the local time occurred twice; ignored
        otherwise.
    """

    local_date: date
    local_time: time
    place_id: str
    ambiguous_time: AmbiguousTimeChoice | None = None


def local_birth_to_utc(birth: BirthData, zone: ZoneInfo) -> datetime:
    """Convert the local birthdate and time to an aware UTC instant.

    Uses the zone's full history from the IANA database, so historical offsets and DST rules
    of the birthdate apply, not today's.

    :param birth: Local birthdate and time.
    :param zone: Time zone of the birthplace.
    :returns: The birth instant in UTC.
    :raises InvalidBirthDataError: If the local time does not exist (skipped when clocks moved
        forward), or occurred twice and ``birth.ambiguous_time`` is not set.
    """
    wall_clock = datetime.combine(birth.local_date, birth.local_time)
    earlier = wall_clock.replace(tzinfo=zone, fold=0)
    later = wall_clock.replace(tzinfo=zone, fold=1)
    if earlier.utcoffset() == later.utcoffset():
        return earlier.astimezone(UTC)
    # Offsets differ only at a transition: in a gap the wall time does not survive a round trip
    # through UTC; in an overlap it does, and fold picks the instant.
    if earlier.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != wall_clock:
        raise InvalidBirthDataError(_NONEXISTENT_TIME_MESSAGE)
    if birth.ambiguous_time is None:
        raise InvalidBirthDataError(_AMBIGUOUS_TIME_MESSAGE)
    chosen = earlier if birth.ambiguous_time is AmbiguousTimeChoice.EARLIER else later
    return chosen.astimezone(UTC)


def require_birth_not_in_future(birth_utc: datetime, *, now: datetime) -> None:
    """Reject a birth instant after the current instant.

    Compares instants, not dates, so a birth earlier today in a zone ahead of UTC is accepted.

    :param birth_utc: Aware birth instant, e.g. from :func:`local_birth_to_utc`.
    :param now: Aware current instant; passed in so this function stays pure.
    :raises ValueError: If either argument is naive; a programming error, not bad input.
    :raises InvalidBirthDataError: If the birth instant is after ``now``.
    """
    if birth_utc.tzinfo is None or now.tzinfo is None:
        msg = "birth_utc and now must be timezone-aware"
        raise ValueError(msg)
    if birth_utc > now:
        raise InvalidBirthDataError(_FUTURE_BIRTH_MESSAGE)
