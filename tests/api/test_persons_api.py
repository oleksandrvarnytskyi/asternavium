# SPDX-License-Identifier: AGPL-3.0-or-later
# All birth data here is synthetic; none of it belongs to a real person.
from typing import Any

import pytest
from api_helpers import (
    ALICE,
    BIRTH,
    BOB,
    PARIS_TEXAS,
    UNKNOWN_ID,
    create_person,
    save_profile,
)
from fastapi.testclient import TestClient

from app.schemas.persons import PERSON_LABEL_MAX_LENGTH

PERSONS_PATH = "/v1/persons"
BIRTH_IN_TEXAS = {"date": "1985-11-02", "time": "06:05", "place_id": PARIS_TEXAS}


def _labels(client: TestClient, headers: dict[str, str] = ALICE) -> list[str]:
    response = client.get(PERSONS_PATH, headers=headers)
    return [person["label"] for person in response.json()["items"]]


def _post(
    client: TestClient, birth_changes: dict[str, Any] | None = None, *, label: str = "Me"
) -> Any:
    """Post a person with the valid birth data changed by ``birth_changes``."""
    birth = {**BIRTH, **(birth_changes or {})}
    return client.post(PERSONS_PATH, headers=ALICE, json={"label": label, "birth": birth})


def test_create_person_returns_saved_place_and_utc_instant(api_client: TestClient) -> None:
    response = api_client.post(
        PERSONS_PATH, headers=ALICE, json={"label": "Mum", "birth": BIRTH_IN_TEXAS}
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"person_id", "label", "birth", "created_at", "updated_at"}
    assert body["label"] == "Mum"
    assert body["birth"] == {
        "date": "1985-11-02",
        "time": "06:05",
        "ambiguous_time": None,
        "place": {
            "place_id": PARIS_TEXAS,
            "name": "Paris",
            "region": "Texas",
            "country": "United States",
            "timezone": "America/Chicago",
        },
        # Central Standard Time, UTC-6.
        "instant_utc": "1985-11-02T12:05:00Z",
    }


def test_create_person_trims_label(api_client: TestClient) -> None:
    assert create_person(api_client, label="  Mum  ")["label"] == "Mum"


@pytest.mark.parametrize(
    "label",
    [pytest.param("   ", id="blank"), pytest.param("x" * (PERSON_LABEL_MAX_LENGTH + 1), id="long")],
)
def test_create_person_rejects_invalid_label(api_client: TestClient, label: str) -> None:
    response = _post(api_client, label=label)

    assert response.status_code == 422
    assert response.json()["details"][0]["loc"] == ["body", "label"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("date", 19900517, id="date-as-number"),
        pytest.param("time", 52200, id="time-as-seconds"),
        pytest.param("time", "14:30:15", id="time-with-seconds"),
        pytest.param("latitude", 50.45, id="coordinates"),
    ],
)
def test_create_person_rejects_malformed_birth(
    api_client: TestClient, field: str, value: object
) -> None:
    response = _post(api_client, {field: value})

    assert response.status_code == 422
    assert response.json()["details"][0]["loc"] == ["body", "birth", field]


def test_create_person_error_does_not_echo_birth_data(api_client: TestClient) -> None:
    response = _post(api_client, {"date": "1990-13-45", "time": "14:30:15"})

    assert response.status_code == 422
    assert "1990-13-45" not in response.text
    assert "14:30" not in response.text


def test_create_person_with_unknown_place_returns_place_not_found(api_client: TestClient) -> None:
    response = _post(api_client, {"place_id": "999999"})

    assert response.status_code == 422
    assert response.json()["code"] == "place_not_found"
    assert _labels(api_client) == []


def test_create_person_with_time_skipped_by_dst_returns_invalid_birth_data(
    api_client: TestClient,
) -> None:
    # Clocks in Kyiv moved from 03:00 to 04:00 on 2021-03-28.
    response = _post(api_client, {"date": "2021-03-28", "time": "03:30"})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_birth_data"


def test_create_person_with_ambiguous_time_needs_choice(api_client: TestClient) -> None:
    # Clocks in Kyiv moved from 04:00 back to 03:00 on 2021-10-31.
    ambiguous = {"date": "2021-10-31", "time": "03:30"}

    without_choice = _post(api_client, ambiguous)
    with_choice = _post(api_client, {**ambiguous, "ambiguous_time": "earlier"})

    assert without_choice.json()["code"] == "invalid_birth_data"
    assert with_choice.status_code == 201
    # The earlier 03:30 is still summer time, UTC+3.
    assert with_choice.json()["birth"]["instant_utc"] == "2021-10-31T00:30:00Z"


def test_list_persons_pages_own_persons_newest_first(api_client: TestClient) -> None:
    for label in ("First", "Second", "Third"):
        create_person(api_client, label=label)
    create_person(api_client, BOB, label="Bob's")

    first = api_client.get(PERSONS_PATH, headers=ALICE, params={"limit": 2}).json()
    second = api_client.get(
        PERSONS_PATH, headers=ALICE, params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()

    assert [person["label"] for person in first["items"]] == ["Third", "Second"]
    assert [person["label"] for person in second["items"]] == ["First"]
    assert second["next_cursor"] is None


def test_list_persons_rejects_malformed_cursor(api_client: TestClient) -> None:
    response = api_client.get(PERSONS_PATH, headers=ALICE, params={"cursor": "not-a-cursor"})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_cursor"


def test_get_person_returns_it(api_client: TestClient) -> None:
    person = create_person(api_client)

    response = api_client.get(f"{PERSONS_PATH}/{person['person_id']}", headers=ALICE)

    assert response.status_code == 200
    assert response.json() == person


@pytest.mark.parametrize("person_id", [pytest.param(UNKNOWN_ID, id="unknown"), "other-user"])
def test_get_person_not_owned_returns_not_found(api_client: TestClient, person_id: str) -> None:
    person = create_person(api_client, BOB)
    target = person["person_id"] if person_id == "other-user" else person_id

    response = api_client.get(f"{PERSONS_PATH}/{target}", headers=ALICE)

    assert response.status_code == 404
    assert response.json()["code"] == "person_not_found"


def test_get_person_rejects_malformed_id(api_client: TestClient) -> None:
    response = api_client.get(f"{PERSONS_PATH}/not-an-id", headers=ALICE)

    assert response.status_code == 422


def test_replace_person_updates_it_and_keeps_creation_time(api_client: TestClient) -> None:
    person = create_person(api_client)
    path = f"{PERSONS_PATH}/{person['person_id']}"

    response = api_client.put(path, headers=ALICE, json={"label": "Mum", "birth": BIRTH_IN_TEXAS})

    assert response.status_code == 200
    body = response.json()
    assert (body["person_id"], body["label"], body["birth"]["place"]["region"]) == (
        person["person_id"],
        "Mum",
        "Texas",
    )
    assert body["created_at"] == person["created_at"]
    assert api_client.get(path, headers=ALICE).json() == body


def test_replace_other_users_person_returns_not_found(api_client: TestClient) -> None:
    person = create_person(api_client)
    path = f"{PERSONS_PATH}/{person['person_id']}"

    response = api_client.put(path, headers=BOB, json={"label": "Hijacked", "birth": BIRTH})

    assert response.status_code == 404
    assert response.json()["code"] == "person_not_found"
    assert api_client.get(path, headers=ALICE).json() == person


def test_delete_person_removes_it(api_client: TestClient) -> None:
    person = create_person(api_client)
    path = f"{PERSONS_PATH}/{person['person_id']}"

    response = api_client.delete(path, headers=ALICE)

    assert response.status_code == 204
    assert api_client.get(path, headers=ALICE).status_code == 404
    assert api_client.delete(path, headers=ALICE).status_code == 204


def test_delete_other_users_person_leaves_it(api_client: TestClient) -> None:
    person = create_person(api_client)
    path = f"{PERSONS_PATH}/{person['person_id']}"

    response = api_client.delete(path, headers=BOB)

    assert response.status_code == 204
    assert api_client.get(path, headers=ALICE).json() == person


def test_delete_owner_person_clears_profile_link(api_client: TestClient) -> None:
    owner = create_person(api_client)
    save_profile(api_client, owner_person_id=owner["person_id"])

    api_client.delete(f"{PERSONS_PATH}/{owner['person_id']}", headers=ALICE)

    profile = api_client.get("/v1/me", headers=ALICE).json()["profile"]
    assert profile["owner_person_id"] is None
