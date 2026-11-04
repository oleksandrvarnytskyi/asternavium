# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request model for birth data."""

import datetime as dt
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.birth_data import EARLIEST_BIRTH_DATE, AmbiguousTimeChoice, BirthData

# Long enough for any place ID source, including provider IDs of managed geocoding services.
PLACE_ID_MAX_LENGTH: Final = 500


class BirthDataInput(BaseModel):
    """Birthdate, time and place as entered by the user, in the birthplace's local time.

    Coordinates and time zone are not accepted: the server takes them from the chosen place.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    date: dt.date = Field(
        strict=True,
        ge=EARLIEST_BIRTH_DATE,
        description=f"Local birth date from {EARLIEST_BIRTH_DATE.isoformat()} on, e.g. "
        "``1990-05-17``; a date in the future is rejected when the profile is saved.",
    )
    time: dt.time = Field(
        strict=True,
        description="Local wall-clock birth time to the minute, e.g. ``14:30``; no UTC offset.",
    )
    place_id: str = Field(
        min_length=1, max_length=PLACE_ID_MAX_LENGTH, description="Place ID from GET /v1/places."
    )
    ambiguous_time: AmbiguousTimeChoice | None = Field(
        default=None,
        description="Required only if the birth time occurred twice because clocks were set "
        "back: ``earlier`` or ``later``.",
    )

    @field_validator("time")
    @classmethod
    def _check_time_is_local_and_to_the_minute(cls, value: dt.time) -> dt.time:
        """Reject offsets, which belong to the place, and seconds, which are not collected."""
        if value.tzinfo is not None:
            msg = "must not include a UTC offset; the birth place sets the time zone"
            raise ValueError(msg)
        if value.second or value.microsecond:
            msg = "must be given to the minute, without seconds"
            raise ValueError(msg)
        return value

    def to_birth_data(self) -> BirthData:
        """Return the validated input as a domain value."""
        return BirthData(
            local_date=self.date,
            local_time=self.time,
            place_id=self.place_id,
            ambiguous_time=self.ambiguous_time,
        )
