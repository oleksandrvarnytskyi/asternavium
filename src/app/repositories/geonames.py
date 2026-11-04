# SPDX-License-Identifier: AGPL-3.0-or-later
"""Place search over the GeoNames snapshot bundled in ``app.data.places``.

The snapshot is built by ``tools/geonames_snapshot.py``: gzip-compressed, tab-separated rows in
:class:`SnapshotColumn` order, with alternate names separated by commas, plus a version file
holding the download date. GeoNames data is licensed under CC BY 4.0 (see ``NOTICE``).
"""

import gzip
import heapq
import logging
import time
import unicodedata
from array import array
from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum
from importlib.resources import files
from typing import Final

from app.repositories.places import Place

logger = logging.getLogger(__name__)

SNAPSHOT_PACKAGE: Final = "app.data.places"
SNAPSHOT_FILE_NAME: Final = "cities500.tsv.gz"
VERSION_FILE_NAME: Final = "version.txt"
FIELD_SEPARATOR: Final = "\t"
NAME_SEPARATOR: Final = ","
# Unsigned 32-bit integers: compact storage for one place position per name in the index.
_POSITION_TYPECODE: Final = "I"


class SnapshotColumn(IntEnum):
    """Column positions in a snapshot row."""

    PLACE_ID = 0
    NAME = 1
    ASCII_NAME = 2
    ALTERNATE_NAMES = 3
    REGION = 4
    COUNTRY = 5
    LATITUDE = 6
    LONGITUDE = 7
    POPULATION = 8
    TIMEZONE = 9


class MatchTier(IntEnum):
    """How well a place matched a search; higher ranks first."""

    ALTERNATE_NAME = 0
    MAIN_NAME = 1


@dataclass(frozen=True, slots=True)
class GeoNamesRecord:
    """A place together with every name it can be found by; empty names are ignored.

    :ivar place: The place returned to callers.
    :ivar main_names: Display and ASCII names.
    :ivar alternate_names: Other names in any script, including nicknames and historic names,
        which is why they rank below main names.
    """

    place: Place
    main_names: tuple[str, ...]
    alternate_names: tuple[str, ...]


def normalize_place_name(text: str) -> str:
    """Fold case, remove accents and collapse whitespace, so spelling variants compare equal.

    "Kyiv", "KYIV" and "Kýiv" all become "kyiv"; Cyrillic "Київ" becomes "киів".
    """
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.split())


def parse_snapshot_row(line: str) -> GeoNamesRecord:
    """Parse one snapshot row.

    :raises ValueError: If a numeric column is malformed.
    :raises IndexError: If the row has too few columns.
    """
    fields = line.split(FIELD_SEPARATOR)
    place = Place(
        place_id=fields[SnapshotColumn.PLACE_ID],
        name=fields[SnapshotColumn.NAME],
        region=fields[SnapshotColumn.REGION] or None,
        country=fields[SnapshotColumn.COUNTRY],
        latitude=float(fields[SnapshotColumn.LATITUDE]),
        longitude=float(fields[SnapshotColumn.LONGITUDE]),
        population=int(fields[SnapshotColumn.POPULATION]),
        timezone=fields[SnapshotColumn.TIMEZONE],
    )
    return GeoNamesRecord(
        place=place,
        main_names=(fields[SnapshotColumn.NAME], fields[SnapshotColumn.ASCII_NAME]),
        alternate_names=tuple(fields[SnapshotColumn.ALTERNATE_NAMES].split(NAME_SEPARATOR)),
    )


def _index_entries(record: GeoNamesRecord, position: int) -> list[tuple[str, int, MatchTier]]:
    """Return one entry per distinct normalized name, keeping the best tier for each.

    :param position: Index of the record's place in dataset order.
    """
    tiers: dict[str, MatchTier] = {}
    for tier, names in (
        (MatchTier.ALTERNATE_NAME, record.alternate_names),
        (MatchTier.MAIN_NAME, record.main_names),
    ):
        for name in names:
            if key := normalize_place_name(name):
                tiers[key] = tier
    return [(key, position, tier) for key, tier in tiers.items()]


class GeoNamesPlaceRepository:
    """In-memory :class:`~app.repositories.places.PlaceRepository` over GeoNames records.

    Every normalized name of every place goes into one sorted list, so a prefix search is a
    binary search followed by a scan of the matching range. Places matching by main name rank
    above places matching only by an alternate name; within a tier, larger population first,
    then earlier in dataset order (the snapshot is sorted by GeoNames ID). Search is CPU-bound
    and synchronous.
    """

    def __init__(self, records: Iterable[GeoNamesRecord], *, dataset_version: str) -> None:
        self._dataset_version = dataset_version
        self._places: list[Place] = []
        self._positions: dict[str, int] = {}
        entries: list[tuple[str, int, MatchTier]] = []
        for position, record in enumerate(records):
            self._places.append(record.place)
            self._positions[record.place.place_id] = position
            entries.extend(_index_entries(record, position))
        entries.sort()
        self._keys = [key for key, _, _ in entries]
        self._key_positions = array(_POSITION_TYPECODE, (position for _, position, _ in entries))
        self._key_tiers = bytes(tier for _, _, tier in entries)

    @property
    def dataset_version(self) -> str:
        """Download date of the GeoNames data, e.g. ``2026-11-04``."""
        return self._dataset_version

    def __len__(self) -> int:
        """Return the number of places."""
        return len(self._places)

    def search(self, query: str, *, limit: int) -> list[Place]:
        """Find places with a name starting with ``query``, ignoring case and accents.

        :param query: Name prefix as typed by the user; blank after normalization matches nothing.
        :param limit: Maximum number of places to return; positive.
        :returns: Main-name matches before alternate-name matches, each by largest population,
            then dataset order.
        """
        prefix = normalize_place_name(query)
        if not prefix:
            return []
        best_tiers: dict[int, int] = {}
        for index in range(bisect_left(self._keys, prefix), len(self._keys)):
            if not self._keys[index].startswith(prefix):
                break
            position = self._key_positions[index]
            best_tiers[position] = max(best_tiers.get(position, 0), self._key_tiers[index])
        ranked = heapq.nlargest(
            limit,
            best_tiers.items(),
            key=lambda match: self._rank(position=match[0], tier=match[1]),
        )
        return [self._places[position] for position, _ in ranked]

    def _rank(self, *, position: int, tier: int) -> tuple[int, int, int]:
        """Sort key, highest first: match tier, population, then earlier dataset position."""
        return tier, self._places[position].population, -position

    def get(self, place_id: str) -> Place | None:
        """Return the place with this GeoNames ID, or ``None`` if the dataset has no such place."""
        position = self._positions.get(place_id)
        return None if position is None else self._places[position]


def load_geonames_repository() -> GeoNamesPlaceRepository:
    """Load the bundled snapshot and index it.

    .. note:: Takes about three seconds and 150 MB for the ~226,000 places of ``cities500``, so
       call it once at startup.

    :raises FileNotFoundError: If the snapshot is missing; run ``make places-snapshot``.
    """
    started = time.perf_counter()
    package = files(SNAPSHOT_PACKAGE)
    text = gzip.decompress(package.joinpath(SNAPSHOT_FILE_NAME).read_bytes()).decode("utf-8")
    version = package.joinpath(VERSION_FILE_NAME).read_text(encoding="utf-8").strip()
    repository = GeoNamesPlaceRepository(
        (parse_snapshot_row(line) for line in text.splitlines()), dataset_version=version
    )
    logger.info(
        "Loaded %d places from GeoNames %s in %.1f s",
        len(repository),
        version,
        time.perf_counter() - started,
    )
    return repository
