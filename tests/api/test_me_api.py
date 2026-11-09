# SPDX-License-Identifier: AGPL-3.0-or-later
import anyio
from api_helpers import ALICE, BOB, create_person, create_session, save_profile
from fastapi.testclient import TestClient

from app.repositories.dynamodb_messages import DynamoDBMessageRepository
from app.repositories.dynamodb_persons import DynamoDBPersonRepository

ME_PATH = "/v1/me"


def _create_account(client: TestClient, headers: dict[str, str]) -> str:
    """Give the user a person, a profile linked to it and a session; return the session ID."""
    person = create_person(client, headers)
    save_profile(client, headers, owner_person_id=person["person_id"])
    return str(create_session(client, headers)["session_id"])


def _item_counts(client: TestClient, headers: dict[str, str]) -> tuple[int, int]:
    persons = client.get("/v1/persons", headers=headers).json()["items"]
    sessions = client.get("/v1/sessions", headers=headers).json()["items"]
    return len(persons), len(sessions)


def test_get_me_before_profile_returns_null_profile(api_client: TestClient) -> None:
    response = api_client.get(ME_PATH, headers=ALICE)

    assert response.status_code == 200
    assert response.json() == {"user_id": "alice", "profile": None}


def test_get_me_returns_saved_profile(api_client: TestClient) -> None:
    profile = save_profile(api_client, traditions=["bukvitsa"])

    assert api_client.get(ME_PATH, headers=ALICE).json() == {"user_id": "alice", "profile": profile}


def test_get_me_reports_link_to_deleted_person_as_null(
    api_client: TestClient, persons: DynamoDBPersonRepository
) -> None:
    person = create_person(api_client)
    save_profile(api_client, owner_person_id=person["person_id"])
    # Deleting through the repository leaves the link behind, as a race with a profile save can.
    anyio.run(persons.delete, "alice", person["person_id"])

    profile = api_client.get(ME_PATH, headers=ALICE).json()["profile"]

    assert profile["owner_person_id"] is None


def test_delete_me_removes_all_data_of_the_user(
    api_client: TestClient, messages: DynamoDBMessageRepository
) -> None:
    session_id = _create_account(api_client, ALICE)

    response = api_client.delete(ME_PATH, headers=ALICE)

    assert response.status_code == 204
    assert api_client.get(ME_PATH, headers=ALICE).json()["profile"] is None
    assert _item_counts(api_client, ALICE) == (0, 0)
    page = anyio.run(lambda: messages.list_page(session_id, limit=10, cursor=None))
    assert page.items == ()


def test_delete_me_leaves_other_users_data(api_client: TestClient) -> None:
    _create_account(api_client, ALICE)
    _create_account(api_client, BOB)

    api_client.delete(ME_PATH, headers=ALICE)

    assert api_client.get(ME_PATH, headers=BOB).json()["profile"] is not None
    assert _item_counts(api_client, BOB) == (1, 1)


def test_delete_me_without_data_returns_no_content(api_client: TestClient) -> None:
    assert api_client.delete(ME_PATH, headers=ALICE).status_code == 204
