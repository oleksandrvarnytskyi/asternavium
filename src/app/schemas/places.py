# SPDX-License-Identifier: AGPL-3.0-or-later
"""Models for birth place search."""

from pydantic import BaseModel, ConfigDict, Field


class PlaceSummary(BaseModel):
    """A place offered to the user as a birth place; coordinates stay on the server."""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    place_id: str = Field(
        description="Opaque ID that identifies the place in later requests; do not parse it."
    )
    name: str = Field(description="Display name.")
    region: str | None = Field(description="State, oblast or other region, if known.")
    country: str = Field(description="Country name in English.")
    timezone: str = Field(description="IANA time zone name, e.g. ``Europe/Kyiv``.")


class PlaceSearchResponse(BaseModel):
    """Places matching a search, largest population first."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[PlaceSummary] = Field(description="Matching places; empty if none match.")
