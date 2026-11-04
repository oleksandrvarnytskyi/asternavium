# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rebuild the bundled GeoNames places snapshot.

Run ``make places-snapshot``, then commit both output files. It downloads ``cities500``, the
first-level region names and the country names from the GeoNames export (CC BY 4.0), drops city
districts, keeps only the columns the app needs, resolves region and country codes to names,
and writes the snapshot with its version (the download date, UTC) to ``src/app/data/places/``.
Output is byte-for-byte reproducible for the same input, so an unchanged dataset produces no
diff.
"""

import argparse
import gzip
import io
import logging
import urllib.request
import zipfile
import zoneinfo
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import Final

from app.core.config import LogLevel
from app.core.logging import configure_logging
from app.repositories.geonames import (
    FIELD_SEPARATOR,
    SNAPSHOT_FILE_NAME,
    VERSION_FILE_NAME,
    SnapshotColumn,
)

logger = logging.getLogger(__name__)

GEONAMES_EXPORT_URL: Final = "https://download.geonames.org/export/dump/"
CITIES_ARCHIVE: Final = "cities500.zip"
CITIES_FILE: Final = "cities500.txt"
REGIONS_FILE: Final = "admin1CodesASCII.txt"
COUNTRIES_FILE: Final = "countryInfo.txt"
DOWNLOAD_TIMEOUT_SECONDS: Final = 120
DEFAULT_OUTPUT_DIR: Final = Path(__file__).resolve().parents[1] / "src/app/data/places"
COMMENT_PREFIX: Final = "#"
REGION_KEY_SEPARATOR: Final = "."
# Sections of a populated place (city districts such as Paris arrondissements). Excluded so the
# city itself is the birth place; to be confirmed before launch (specification, section 13).
EXCLUDED_FEATURE_CODES: Final = frozenset({"PPLX"})
GZIP_LEVEL: Final = 9


class CitiesColumn(IntEnum):
    """Column positions in GeoNames ``cities500.txt`` used by the snapshot."""

    GEONAME_ID = 0
    NAME = 1
    ASCII_NAME = 2
    ALTERNATE_NAMES = 3
    LATITUDE = 4
    LONGITUDE = 5
    FEATURE_CODE = 7
    COUNTRY_CODE = 8
    ADMIN1_CODE = 10
    POPULATION = 14
    TIMEZONE = 17


class RegionsColumn(IntEnum):
    """Column positions in GeoNames ``admin1CodesASCII.txt``."""

    CODE = 0
    NAME = 1


class CountriesColumn(IntEnum):
    """Column positions in GeoNames ``countryInfo.txt``."""

    ISO_CODE = 0
    NAME = 4


def download(file_name: str) -> bytes:
    """Download one file from the GeoNames export.

    :raises urllib.error.URLError: On network failure or a non-2xx response; rerun the tool.
    """
    url = GEONAMES_EXPORT_URL + file_name
    logger.info("Downloading %s", url)
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed https URL
        data: bytes = response.read()
    return data


def parse_lookup(text: str, *, key_column: int, value_column: int) -> dict[str, str]:
    """Map one column of a tab-separated GeoNames file to another, skipping comment lines."""
    lookup: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith(COMMENT_PREFIX):
            continue
        fields = line.split(FIELD_SEPARATOR)
        lookup[fields[key_column]] = fields[value_column]
    return lookup


def build_snapshot_row(
    source: Sequence[str],
    *,
    regions: Mapping[str, str],
    countries: Mapping[str, str],
    timezones: frozenset[str],
) -> tuple[int, str]:
    """Convert one ``cities500`` row into a snapshot row.

    :param source: Fields of the ``cities500`` line.
    :param regions: Region names keyed by ``<country code>.<admin1 code>``.
    :param countries: Country names keyed by ISO 3166 alpha-2 code.
    :param timezones: IANA zone names known to the installed ``tzdata``.
    :returns: Place ID, for sorting, and the row.
    :raises ValueError: If the country or the time zone is unknown; update ``tzdata`` for the
        latter.
    """
    place_id = int(source[CitiesColumn.GEONAME_ID])
    country_code = source[CitiesColumn.COUNTRY_CODE]
    timezone = source[CitiesColumn.TIMEZONE]
    if country_code not in countries:
        msg = f"Place {place_id}: unknown country code {country_code!r}"
        raise ValueError(msg)
    if timezone not in timezones:
        msg = f"Place {place_id}: time zone {timezone!r} is not in tzdata; update tzdata"
        raise ValueError(msg)
    region_key = f"{country_code}{REGION_KEY_SEPARATOR}{source[CitiesColumn.ADMIN1_CODE]}"

    fields = [""] * len(SnapshotColumn)
    fields[SnapshotColumn.PLACE_ID] = str(place_id)
    fields[SnapshotColumn.NAME] = source[CitiesColumn.NAME]
    fields[SnapshotColumn.ASCII_NAME] = source[CitiesColumn.ASCII_NAME]
    fields[SnapshotColumn.ALTERNATE_NAMES] = source[CitiesColumn.ALTERNATE_NAMES]
    fields[SnapshotColumn.REGION] = regions.get(region_key, "")
    fields[SnapshotColumn.COUNTRY] = countries[country_code]
    fields[SnapshotColumn.LATITUDE] = source[CitiesColumn.LATITUDE]
    fields[SnapshotColumn.LONGITUDE] = source[CitiesColumn.LONGITUDE]
    fields[SnapshotColumn.POPULATION] = source[CitiesColumn.POPULATION]
    fields[SnapshotColumn.TIMEZONE] = timezone
    return place_id, FIELD_SEPARATOR.join(fields)


def build_snapshot(
    cities_text: str, *, regions: Mapping[str, str], countries: Mapping[str, str]
) -> list[str]:
    """Convert ``cities500`` lines into snapshot rows sorted by place ID, skipping city districts.

    :raises ValueError: If any place has an unknown country or time zone.
    """
    timezones = frozenset(zoneinfo.available_timezones())
    sources = (line.split(FIELD_SEPARATOR) for line in cities_text.splitlines() if line)
    rows = [
        build_snapshot_row(source, regions=regions, countries=countries, timezones=timezones)
        for source in sources
        if source[CitiesColumn.FEATURE_CODE] not in EXCLUDED_FEATURE_CODES
    ]
    return [row for _, row in sorted(rows)]


def write_snapshot(rows: Sequence[str], *, output_dir: Path, version: str) -> None:
    """Write the gzip-compressed snapshot and its version file.

    The gzip header carries no timestamp, so identical rows always produce identical bytes.
    """
    data = "".join(f"{row}\n" for row in rows).encode("utf-8")
    snapshot = output_dir / SNAPSHOT_FILE_NAME
    snapshot.write_bytes(gzip.compress(data, compresslevel=GZIP_LEVEL, mtime=0))
    (output_dir / VERSION_FILE_NAME).write_text(f"{version}\n", encoding="utf-8")
    logger.info(
        "Wrote %d places to %s (%.1f MB), version %s",
        len(rows),
        snapshot,
        snapshot.stat().st_size / 1_000_000,
        version,
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Download the GeoNames files and rebuild the snapshot."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    configure_logging(LogLevel.INFO)

    version = datetime.now(UTC).date().isoformat()
    with zipfile.ZipFile(io.BytesIO(download(CITIES_ARCHIVE))) as archive:
        cities_text = archive.read(CITIES_FILE).decode("utf-8")
    regions = parse_lookup(
        download(REGIONS_FILE).decode("utf-8"),
        key_column=RegionsColumn.CODE,
        value_column=RegionsColumn.NAME,
    )
    countries = parse_lookup(
        download(COUNTRIES_FILE).decode("utf-8"),
        key_column=CountriesColumn.ISO_CODE,
        value_column=CountriesColumn.NAME,
    )
    rows = build_snapshot(cities_text, regions=regions, countries=countries)
    write_snapshot(rows, output_dir=args.output_dir, version=version)


if __name__ == "__main__":
    main()
