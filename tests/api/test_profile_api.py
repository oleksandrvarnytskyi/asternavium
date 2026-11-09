# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from api_helpers import ALICE, BOB, UNKNOWN_ID, create_person, save_profile
from fastapi.testclient import TestClient

PROFILE_PATH = "/v1/profile"


def test_replace_profile_without_fields_saves_defaults(api_client: TestClient) -> None:
    profile = save_profile(api_client)

    assert set(profile) == {
        "locale",
        "traditions",
        "answer_depth",
        "owner_person_id",
        "created_at",
        "updated_at",
    }
    assert (
        profile["locale"],
        profile["traditions"],
        profile["answer_depth"],
        profile["owner_person_id"],
    ) == ("en", ["jyotisha"], "simple", None)


def test_replace_profile_returns_traditions_sorted(api_client: TestClient) -> None:
    profile = save_profile(
        api_client,
        locale="sr-Latn-RS",
        traditions=["jyotisha", "bukvitsa"],
        answer_depth="technical",
    )

    assert (profile["locale"], profile["traditions"], profile["answer_depth"]) == (
        "sr-Latn-RS",
        ["bukvitsa", "jyotisha"],
        "technical",
    )


def test_replace_profile_again_keeps_creation_time(api_client: TestClient) -> None:
    first = save_profile(api_client)

    second = save_profile(api_client, answer_depth="detailed")

    assert second["created_at"] == first["created_at"]
    assert second["answer_depth"] == "detailed"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"traditions": []}, id="no-traditions"),
        pytest.param({"traditions": ["jyotisha", "jyotisha"]}, id="repeated-tradition"),
        pytest.param({"traditions": ["tarot"]}, id="unknown-tradition"),
        pytest.param({"locale": "english"}, id="malformed-locale"),
        pytest.param({"answer_depth": "essentials"}, id="unknown-depth"),
        pytest.param({"owner_person_id": "not-an-id"}, id="malformed-person-id"),
        pytest.param({"birth": {}}, id="extra-field"),
    ],
)
def test_replace_profile_rejects_invalid_body(
    api_client: TestClient, payload: dict[str, object]
) -> None:
    response = api_client.put(PROFILE_PATH, headers=ALICE, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_replace_profile_links_own_person(api_client: TestClient) -> None:
    person = create_person(api_client)

    profile = save_profile(api_client, owner_person_id=person["person_id"])

    assert profile["owner_person_id"] == person["person_id"]


@pytest.mark.parametrize("owner", ["unknown", "other-user"])
def test_replace_profile_with_person_not_owned_returns_not_found(
    api_client: TestClient, owner: str
) -> None:
    person_id = create_person(api_client, BOB)["person_id"] if owner == "other-user" else UNKNOWN_ID

    response = api_client.put(PROFILE_PATH, headers=ALICE, json={"owner_person_id": person_id})

    assert response.status_code == 404
    assert response.json()["code"] == "person_not_found"
    assert api_client.get("/v1/me", headers=ALICE).json()["profile"] is None
