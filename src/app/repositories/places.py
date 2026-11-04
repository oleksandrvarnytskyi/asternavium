# SPDX-License-Identifier: AGPL-3.0-or-later
"""Birthplace value type and the read-only repository interface for looking places up."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Place:
    """A populated place a birth can be located at.

    :ivar place_id: Opaque ID from the place data source (today the GeoNames ID as a decimal
        string); a string, so a different source with non-numeric IDs fits without migration.
    :ivar name: Display name as published by GeoNames.
    :ivar region: First-level administrative division (state, oblast), if GeoNames has one.
    :ivar country: Country name in English.
    :ivar latitude: Degrees north of the equator, -90 to 90 (WGS84).
    :ivar longitude: Degrees east of Greenwich, -180 to 180 (WGS84).
    :ivar population: Number of inhabitants; 0 when GeoNames has no figure.
    :ivar timezone: IANA time zone name, e.g. ``Europe/Kyiv``.
    """

    place_id: str
    name: str
    region: str | None
    country: str
    latitude: float
    longitude: float
    population: int
    timezone: str


class PlaceRepository(Protocol):
    """Read-only lookup of birthplaces."""

    @property
    def dataset_version(self) -> str:
        """Version of the place data, stored alongside every saved birthplace."""
        ...

    def search(self, query: str, *, limit: int) -> list[Place]:
        """Find places with a name starting with ``query``, ignoring case and accents.

        :param query: Name prefix as typed by the user.
        :param limit: Maximum number of places to return; positive.
        :returns: Matches, largest population first.
        """
        ...

    def get(self, place_id: str) -> Place | None:
        """Return the place with this ID, or ``None`` if the dataset has no such place."""
        ...
