# SPDX-License-Identifier: AGPL-3.0-or-later
import gzip
import io
import zipfile
from pathlib import Path

import pytest

from app.repositories.geonames import (
    FIELD_SEPARATOR,
    SNAPSHOT_FILE_NAME,
    VERSION_FILE_NAME,
    parse_snapshot_row,
)
from app.repositories.places import Place
from tools import geonames_snapshot
from tools.geonames_snapshot import (
    CITIES_ARCHIVE,
    CITIES_FILE,
    COUNTRIES_FILE,
    REGIONS_FILE,
    CitiesColumn,
    build_snapshot,
    parse_lookup,
    write_snapshot,
)

# cities500.txt has 19 tab-separated columns.
CITIES_COLUMN_COUNT = 19
REGIONS = {"UA.12": "Kyiv City", "FR.11": "Île-de-France"}
COUNTRIES = {"UA": "Ukraine", "FR": "France"}
REGIONS_TEXT = "UA.12\tKyiv City\tKyiv City\t703447\nFR.11\tÎle-de-France\tIle-de-France\t3012874\n"
COUNTRIES_TEXT = (
    "#ISO\tISO3\tISO-Numeric\tfips\tCountry\nUA\tUKR\t804\tUP\tUkraine\nFR\tFRA\t250\tFR\tFrance\n"
)


def _cities_line(
    place_id: int,
    name: str,
    *,
    country_code: str = "UA",
    admin1_code: str = "12",
    feature_code: str = "PPL",
    timezone: str = "Europe/Kyiv",
) -> str:
    """Build a cities500 line with the columns the tool reads; others stay empty."""
    fields = [""] * CITIES_COLUMN_COUNT
    fields[CitiesColumn.GEONAME_ID] = str(place_id)
    fields[CitiesColumn.NAME] = name
    fields[CitiesColumn.ASCII_NAME] = name
    fields[CitiesColumn.ALTERNATE_NAMES] = f"{name} Alt,{name} Old"
    fields[CitiesColumn.LATITUDE] = "50.45"
    fields[CitiesColumn.LONGITUDE] = "30.52"
    fields[CitiesColumn.FEATURE_CODE] = feature_code
    fields[CitiesColumn.COUNTRY_CODE] = country_code
    fields[CitiesColumn.ADMIN1_CODE] = admin1_code
    fields[CitiesColumn.POPULATION] = "1000"
    fields[CitiesColumn.TIMEZONE] = timezone
    return FIELD_SEPARATOR.join(fields)


def _build(*lines: str) -> list[str]:
    return build_snapshot("\n".join(lines), regions=REGIONS, countries=COUNTRIES)


def test_parse_lookup_skips_comments_and_blank_lines() -> None:
    lookup = parse_lookup(COUNTRIES_TEXT + "\n", key_column=0, value_column=4)

    assert lookup == COUNTRIES


def test_build_snapshot_row_round_trips_through_app_parser() -> None:
    (row,) = _build(_cities_line(703448, "Kyiv"))

    record = parse_snapshot_row(row)

    assert record.place == Place(
        place_id="703448",
        name="Kyiv",
        region="Kyiv City",
        country="Ukraine",
        latitude=50.45,
        longitude=30.52,
        population=1000,
        timezone="Europe/Kyiv",
    )
    assert record.alternate_names == ("Kyiv Alt", "Kyiv Old")


def test_build_snapshot_leaves_unknown_region_empty() -> None:
    (row,) = _build(_cities_line(1, "Village", admin1_code="99"))

    assert parse_snapshot_row(row).place.region is None


def test_build_snapshot_sorts_rows_by_place_id() -> None:
    rows = _build(_cities_line(30, "C"), _cities_line(4, "A"), _cities_line(200, "B"))

    assert [parse_snapshot_row(row).place.place_id for row in rows] == ["4", "30", "200"]


def test_build_snapshot_drops_city_districts() -> None:
    rows = _build(_cities_line(1, "Kyiv"), _cities_line(2, "Obolon", feature_code="PPLX"))

    assert [parse_snapshot_row(row).place.name for row in rows] == ["Kyiv"]


def test_build_snapshot_rejects_unknown_country() -> None:
    with pytest.raises(ValueError, match="unknown country code"):
        _build(_cities_line(1, "Nowhere", country_code="ZZ"))


def test_build_snapshot_rejects_time_zone_missing_from_tzdata() -> None:
    with pytest.raises(ValueError, match="update tzdata"):
        _build(_cities_line(1, "Nowhere", timezone="Mars/Olympus_Mons"))


def test_write_snapshot_is_reproducible(tmp_path: Path) -> None:
    rows = _build(_cities_line(1, "Kyiv"))
    write_snapshot(rows, output_dir=tmp_path, version="2000-01-01")
    first = (tmp_path / SNAPSHOT_FILE_NAME).read_bytes()

    write_snapshot(rows, output_dir=tmp_path, version="2000-01-01")

    assert (tmp_path / SNAPSHOT_FILE_NAME).read_bytes() == first
    assert gzip.decompress(first).decode("utf-8") == f"{rows[0]}\n"
    assert (tmp_path / VERSION_FILE_NAME).read_text(encoding="utf-8") == "2000-01-01\n"


def test_main_builds_snapshot_from_downloaded_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        cities = [_cities_line(2988507, "Paris", country_code="FR", admin1_code="11")]
        zipped.writestr(CITIES_FILE, "\n".join([*cities, _cities_line(703448, "Kyiv")]))
    downloads = {
        CITIES_ARCHIVE: archive.getvalue(),
        REGIONS_FILE: REGIONS_TEXT.encode("utf-8"),
        COUNTRIES_FILE: COUNTRIES_TEXT.encode("utf-8"),
    }
    monkeypatch.setattr(geonames_snapshot, "download", downloads.__getitem__)

    geonames_snapshot.main(["--output-dir", str(tmp_path)])

    text = gzip.decompress((tmp_path / SNAPSHOT_FILE_NAME).read_bytes()).decode("utf-8")
    places = [parse_snapshot_row(line).place for line in text.splitlines()]
    assert [(place.name, place.region) for place in places] == [
        ("Kyiv", "Kyiv City"),
        ("Paris", "Île-de-France"),
    ]
    assert (tmp_path / VERSION_FILE_NAME).exists()
