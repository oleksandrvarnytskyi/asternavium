# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from fastapi.testclient import TestClient

from app.api.deps import DEV_USER_HEADER
from app.api.v1.places import MAX_LIMIT, QUERY_MAX_LENGTH, QUERY_MIN_LENGTH

PLACES_PATH = "/v1/places"
AUTH = {DEV_USER_HEADER: "alice"}


def test_search_places_requires_dev_identity(client: TestClient) -> None:
    response = client.get(PLACES_PATH, params={"query": "par"})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_search_places_returns_summaries_without_coordinates(client: TestClient) -> None:
    response = client.get(PLACES_PATH, params={"query": "kyiv"}, headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "place_id": "4",
                "name": "Kyiv",
                "region": None,
                "country": "Ukraine",
                "timezone": "Europe/Kyiv",
            }
        ]
    }


def test_search_places_ranks_main_names_by_population_then_alternate_names(
    client: TestClient,
) -> None:
    response = client.get(PLACES_PATH, params={"query": "par"}, headers=AUTH)

    items = response.json()["items"]
    assert [(item["country"], item["region"]) for item in items] == [
        ("France", "Île-de-France"),
        ("United States", "Texas"),
        ("Poland", "Mazovia"),
    ]


def test_search_places_applies_limit(client: TestClient) -> None:
    response = client.get(PLACES_PATH, params={"query": "par", "limit": 1}, headers=AUTH)

    assert [item["place_id"] for item in response.json()["items"]] == ["1"]


def test_search_places_returns_empty_list_without_match(client: TestClient) -> None:
    response = client.get(PLACES_PATH, params={"query": "zurich"}, headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"query": "p" * (QUERY_MIN_LENGTH - 1)},
        {"query": "p" * (QUERY_MAX_LENGTH + 1)},
        {"query": "par", "limit": 0},
        {"query": "par", "limit": MAX_LIMIT + 1},
    ],
)
def test_search_places_rejects_out_of_range_input(
    client: TestClient, params: dict[str, str | int]
) -> None:
    response = client.get(PLACES_PATH, params=params, headers=AUTH)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_search_places_validation_error_does_not_echo_query(client: TestClient) -> None:
    query = "Vlasivka" * 20

    response = client.get(PLACES_PATH, params={"query": query}, headers=AUTH)

    assert response.status_code == 422
    assert "Vlasivka" not in response.text
