# SPDX-License-Identifier: AGPL-3.0-or-later
import re
import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.repositories.geonames import (
    FIELD_SEPARATOR,
    GeoNamesPlaceRepository,
    GeoNamesRecord,
    normalize_place_name,
    parse_snapshot_row,
)
from app.repositories.places import Place

VERSION = "2000-01-01"
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
PARIS_FRANCE_ID = "2988507"
KYIV_ID = "703448"


def _record(
    place_id: str,
    name: str,
    *,
    population: int = 1000,
    alternate_names: tuple[str, ...] = (),
) -> GeoNamesRecord:
    """Build a record whose only distinguishing data are its ID, names and population."""
    place = Place(
        place_id=place_id,
        name=name,
        region=None,
        country="Testland",
        latitude=0.0,
        longitude=0.0,
        population=population,
        timezone="UTC",
    )
    return GeoNamesRecord(place=place, main_names=(name,), alternate_names=alternate_names)


def _repository(*records: GeoNamesRecord) -> GeoNamesPlaceRepository:
    return GeoNamesPlaceRepository(records, dataset_version=VERSION)


def _ids(places: list[Place]) -> list[str]:
    return [place.place_id for place in places]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Kyiv", "kyiv"),
        ("KYIV", "kyiv"),
        ("Kýiv", "kyiv"),
        ("Київ", "киів"),
        ("Straße", "strasse"),
        ("  São   Paulo ", "sao paulo"),
        ("", ""),
    ],
)
def test_normalize_place_name_folds_case_accents_and_spaces(text: str, expected: str) -> None:
    assert normalize_place_name(text) == expected


@given(st.text())
def test_normalize_place_name_leaves_no_marks_or_stray_spaces(text: str) -> None:
    normalized = normalize_place_name(text)

    assert not any(unicodedata.combining(char) for char in normalized)
    assert normalized == " ".join(normalized.split())


def test_parse_snapshot_row_builds_place_and_names() -> None:
    fields = ["42", "Kýiv", "Kyiv", "Київ,Kiev", "Kyiv City", "Ukraine", "50.45", "30.52"]
    line = FIELD_SEPARATOR.join([*fields, "3000", "Europe/Kyiv"])

    record = parse_snapshot_row(line)

    assert record.place == Place(
        place_id="42",
        name="Kýiv",
        region="Kyiv City",
        country="Ukraine",
        latitude=50.45,
        longitude=30.52,
        population=3000,
        timezone="Europe/Kyiv",
    )
    assert record.main_names == ("Kýiv", "Kyiv")
    assert record.alternate_names == ("Київ", "Kiev")


def test_parse_snapshot_row_maps_empty_region_to_none() -> None:
    line = FIELD_SEPARATOR.join(["1", "A", "A", "", "", "Testland", "0", "0", "0", "UTC"])

    assert parse_snapshot_row(line).place.region is None


def test_search_matches_name_prefix() -> None:
    repository = _repository(_record("1", "Paris"), _record("2", "Lyon"))

    assert _ids(repository.search("par", limit=10)) == ["1"]


@pytest.mark.parametrize("query", ["KYIV", "kyïv", "  kyiv ", "Київ"])
def test_search_ignores_case_accents_and_script(query: str) -> None:
    repository = _repository(_record("1", "Kyiv", alternate_names=("Київ",)))

    assert _ids(repository.search(query, limit=10)) == ["1"]


def test_search_ranks_larger_population_first() -> None:
    repository = _repository(
        _record("1", "Paris", population=25_000),
        _record("2", "Paris", population=2_000_000),
    )

    assert _ids(repository.search("paris", limit=10)) == ["2", "1"]


def test_search_ranks_main_name_matches_above_alternate_name_matches() -> None:
    repository = _repository(
        _record("1", "Warsaw", population=1_700_000, alternate_names=("Paris of the North",)),
        _record("2", "Paris", population=25_000),
    )

    assert _ids(repository.search("par", limit=10)) == ["2", "1"]


def test_search_breaks_population_ties_by_dataset_order() -> None:
    repository = _repository(_record("7", "Springfield"), _record("3", "Springfield"))

    assert _ids(repository.search("spring", limit=10)) == ["7", "3"]


def test_search_returns_place_matching_several_names_once() -> None:
    repository = _repository(_record("1", "Kyiv", alternate_names=("Kyjiw", "Kyiv City")))

    assert _ids(repository.search("ky", limit=10)) == ["1"]


def test_search_stops_at_limit() -> None:
    repository = _repository(*(_record(str(i), f"Town {i}", population=i) for i in range(1, 6)))

    assert _ids(repository.search("town", limit=2)) == ["5", "4"]


@pytest.mark.parametrize("query", ["zurich", "   ", "́"])
def test_search_returns_nothing_without_match(query: str) -> None:
    repository = _repository(_record("1", "Paris"))

    assert repository.search(query, limit=10) == []


def test_get_returns_known_place() -> None:
    record = _record("1", "Paris")

    assert _repository(record).get("1") == record.place


def test_get_returns_none_for_unknown_place_id() -> None:
    assert _repository(_record("1", "Paris")).get("999") is None


def test_repository_exposes_dataset_version_and_size() -> None:
    repository = _repository(_record("1", "Paris"), _record("2", "Lyon"))

    assert repository.dataset_version == VERSION
    assert len(repository) == 2


def test_bundled_snapshot_finds_paris_france_first(
    bundled_places: GeoNamesPlaceRepository,
) -> None:
    first = bundled_places.search("par", limit=10)[0]

    assert (first.place_id, first.country, first.timezone) == (
        PARIS_FRANCE_ID,
        "France",
        "Europe/Paris",
    )


def test_bundled_snapshot_finds_kyiv_by_cyrillic_name(
    bundled_places: GeoNamesPlaceRepository,
) -> None:
    assert bundled_places.search("Київ", limit=1)[0].place_id == KYIV_ID


def test_bundled_snapshot_returns_ambiguous_name_in_several_countries(
    bundled_places: GeoNamesPlaceRepository,
) -> None:
    countries = {place.country for place in bundled_places.search("London", limit=5)}

    assert {"United Kingdom", "Canada"} <= countries


def test_bundled_snapshot_excludes_city_districts(
    bundled_places: GeoNamesPlaceRepository,
) -> None:
    # Obolon is a district of Kyiv (GeoNames PPLX); a village of the same name elsewhere stays.
    regions = {place.region for place in bundled_places.search("Obolon", limit=20)}

    assert "Kyiv City" not in regions


def test_bundled_snapshot_has_date_version_and_places(
    bundled_places: GeoNamesPlaceRepository,
) -> None:
    assert ISO_DATE.fullmatch(bundled_places.dataset_version)
    assert bundled_places.get(KYIV_ID) is not None
