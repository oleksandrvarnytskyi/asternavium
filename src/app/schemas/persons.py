# SPDX-License-Identifier: AGPL-3.0-or-later
"""Models for the persons a user makes charts for."""

import datetime as dt
from typing import Annotated, Final, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
)

from app.domain.birth_data import AmbiguousTimeChoice
from app.repositories.records import BirthRecord, PersonRecord
from app.schemas.birth_data import BirthDataInput
from app.schemas.places import PlaceSummary

PERSON_LABEL_MAX_LENGTH: Final = 50
# Birth times are collected to the minute, so they are returned the way they were entered.
_BIRTH_TIME_FORMAT: Final = "%H:%M"

PersonLabel = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=PERSON_LABEL_MAX_LENGTH),
]


class PersonRequest(BaseModel):
    """A person to add or the full replacement of one."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: PersonLabel = Field(
        description=f"Your name for the person, e.g. ``Me`` or ``Mum``; 1 to "
        f"{PERSON_LABEL_MAX_LENGTH} characters after trimming."
    )
    birth: BirthDataInput = Field(description="Birth data in the birthplace's local time.")


class BirthResponse(BaseModel):
    """Birth data as saved; the place is the one chosen when the person was saved."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    date: dt.date = Field(description="Local birth date.")
    time: dt.time = Field(description="Local wall-clock birth time, e.g. ``14:30``.")
    ambiguous_time: AmbiguousTimeChoice | None = Field(
        description="Choice made for a time that occurred twice; ``null`` otherwise."
    )
    place: PlaceSummary = Field(description="Birthplace as it was when the person was saved.")
    instant_utc: AwareDatetime = Field(description="Birth instant in UTC.")

    @field_serializer("time")
    def _format_time(self, value: dt.time) -> str:
        return value.strftime(_BIRTH_TIME_FORMAT)

    @classmethod
    def from_record(cls, birth: BirthRecord) -> Self:
        """Build the response from a stored birth record."""
        return cls(
            date=birth.local_date,
            time=birth.local_time,
            ambiguous_time=birth.ambiguous_time,
            place=PlaceSummary(
                place_id=birth.place_id,
                name=birth.place_name,
                region=birth.place_region,
                country=birth.place_country,
                timezone=birth.timezone,
            ),
            instant_utc=birth.instant_utc,
        )


class PersonResponse(BaseModel):
    """A person of the caller with their birth data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    person_id: str = Field(description="Opaque person ID.")
    label: str = Field(description="Your name for the person.")
    birth: BirthResponse = Field(description="Birth data.")
    created_at: AwareDatetime = Field(description="When the person was added, in UTC.")
    updated_at: AwareDatetime = Field(description="When the person was last replaced, in UTC.")

    @classmethod
    def from_record(cls, person: PersonRecord) -> Self:
        """Build the response from a stored person."""
        return cls(
            person_id=person.person_id,
            label=person.label,
            birth=BirthResponse.from_record(person.birth),
            created_at=person.created_at,
            updated_at=person.updated_at,
        )
