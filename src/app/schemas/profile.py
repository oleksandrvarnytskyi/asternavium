# SPDX-License-Identifier: AGPL-3.0-or-later
"""Models for the profile and the current user."""

from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.domain.profile import (
    DEFAULT_ANSWER_DEPTH,
    DEFAULT_LOCALE,
    DEFAULT_TRADITIONS,
    LOCALE_PATTERN,
    AnswerDepth,
    Tradition,
)
from app.repositories.records import ProfileRecord
from app.schemas.common import ULID_PATTERN


def _default_traditions() -> list[Tradition]:
    return sorted(DEFAULT_TRADITIONS)


class ProfileRequest(BaseModel):
    """The full replacement of the caller's profile; omitted fields take their defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    locale: str = Field(
        default=DEFAULT_LOCALE,
        pattern=LOCALE_PATTERN,
        description="BCP 47 language tag for answers, e.g. ``uk`` or ``sr-Latn-RS``.",
    )
    traditions: list[Tradition] = Field(
        default_factory=_default_traditions,
        min_length=1,
        json_schema_extra={"uniqueItems": True},
        description="Traditions you are interested in; at least one, in any order, no repeats.",
    )
    answer_depth: AnswerDepth = Field(
        default=DEFAULT_ANSWER_DEPTH, description="Default depth of answers."
    )
    owner_person_id: str | None = Field(
        default=None,
        pattern=ULID_PATTERN,
        description="Which of your persons from GET /v1/persons is you; ``null`` for none.",
    )

    @field_validator("traditions")
    @classmethod
    def _check_no_repeats(cls, value: list[Tradition]) -> list[Tradition]:
        if len(set(value)) != len(value):
            msg = "must not repeat a tradition"
            raise ValueError(msg)
        return value


class ProfileResponse(BaseModel):
    """The caller's saved profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    locale: str = Field(description="BCP 47 language tag for answers.")
    traditions: list[Tradition] = Field(
        description="Traditions you are interested in, in alphabetical order."
    )
    answer_depth: AnswerDepth = Field(description="Default depth of answers.")
    owner_person_id: str | None = Field(description="Which of your persons is you, if chosen.")
    created_at: AwareDatetime = Field(description="When the profile was first saved, in UTC.")
    updated_at: AwareDatetime = Field(description="When the profile was last replaced, in UTC.")

    @classmethod
    def from_record(cls, profile: ProfileRecord) -> Self:
        """Build the response from a stored profile."""
        return cls(
            locale=profile.locale,
            traditions=sorted(profile.traditions),
            answer_depth=profile.answer_depth,
            owner_person_id=profile.owner_person_id,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )


class MeResponse(BaseModel):
    """The current user; plan, entitlements and quota are added in Phases 5 and 6."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(description="Your user ID.")
    profile: ProfileResponse | None = Field(
        description="Your profile; ``null`` until the first PUT /v1/profile."
    )
