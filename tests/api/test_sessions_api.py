# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import UTC, datetime

import anyio
import pytest
from api_helpers import ALICE, BOB, UNKNOWN_ID, create_session
from fastapi.testclient import TestClient
from ulid import ULID

from app.api.v1.params import MAX_PAGE_SIZE
from app.domain.chat import DEFAULT_SESSION_TITLE, MessageRole
from app.repositories.dynamodb_messages import DynamoDBMessageRepository
from app.repositories.records import MessageRecord
from app.schemas.sessions import SESSION_TITLE_MAX_LENGTH

SESSIONS_PATH = "/v1/sessions"
WRITTEN_AT = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def _titles(client: TestClient, headers: dict[str, str] = ALICE) -> list[str]:
    response = client.get(SESSIONS_PATH, headers=headers)
    return [session["title"] for session in response.json()["items"]]


def test_create_session_returns_new_empty_session(api_client: TestClient) -> None:
    response = api_client.post(SESSIONS_PATH, headers=ALICE, json={"module": "jyotisha"})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "session_id",
        "title",
        "module",
        "message_count",
        "created_at",
        "updated_at",
    }
    assert (body["title"], body["module"], body["message_count"]) == (
        DEFAULT_SESSION_TITLE,
        "jyotisha",
        0,
    )
    assert body["created_at"] == body["updated_at"]


def test_create_session_trims_title(api_client: TestClient) -> None:
    assert create_session(api_client, title="  Career  ")["title"] == "Career"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"module": "astrology"}, id="unknown-module"),
        pytest.param({}, id="missing-module"),
        pytest.param({"module": "general", "title": "   "}, id="blank-title"),
        pytest.param(
            {"module": "general", "title": "x" * (SESSION_TITLE_MAX_LENGTH + 1)}, id="long-title"
        ),
        pytest.param({"module": "general", "user_id": "bob"}, id="extra-field"),
    ],
)
def test_create_session_rejects_invalid_body(
    api_client: TestClient, payload: dict[str, object]
) -> None:
    response = api_client.post(SESSIONS_PATH, headers=ALICE, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_session_accepts_title_of_max_length(api_client: TestClient) -> None:
    title = "x" * SESSION_TITLE_MAX_LENGTH

    assert create_session(api_client, title=title)["title"] == title


def test_list_sessions_pages_own_sessions_newest_first(api_client: TestClient) -> None:
    for title in ("First", "Second", "Third"):
        create_session(api_client, title=title)
    create_session(api_client, BOB, title="Bob's")

    first = api_client.get(SESSIONS_PATH, headers=ALICE, params={"limit": 2}).json()
    second = api_client.get(
        SESSIONS_PATH, headers=ALICE, params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()

    assert [session["title"] for session in first["items"]] == ["Third", "Second"]
    assert [session["title"] for session in second["items"]] == ["First"]
    assert second["next_cursor"] is None


def test_list_sessions_without_sessions_returns_empty_page(api_client: TestClient) -> None:
    response = api_client.get(SESSIONS_PATH, headers=ALICE)

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


@pytest.mark.parametrize("limit", [0, MAX_PAGE_SIZE + 1])
def test_list_sessions_rejects_limit_out_of_range(api_client: TestClient, limit: int) -> None:
    response = api_client.get(SESSIONS_PATH, headers=ALICE, params={"limit": limit})

    assert response.status_code == 422


def test_list_sessions_rejects_malformed_cursor(api_client: TestClient) -> None:
    response = api_client.get(SESSIONS_PATH, headers=ALICE, params={"cursor": "not-a-cursor"})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_cursor"


def test_rename_session_sets_title(api_client: TestClient) -> None:
    session = create_session(api_client)

    response = api_client.patch(
        f"{SESSIONS_PATH}/{session['session_id']}", headers=ALICE, json={"title": "Renamed"}
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"
    assert _titles(api_client) == ["Renamed"]


def test_rename_other_users_session_returns_not_found(api_client: TestClient) -> None:
    session = create_session(api_client, title="Mine")

    response = api_client.patch(
        f"{SESSIONS_PATH}/{session['session_id']}", headers=BOB, json={"title": "Hijacked"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"
    assert _titles(api_client) == ["Mine"]


def test_rename_unknown_session_returns_not_found(api_client: TestClient) -> None:
    response = api_client.patch(
        f"{SESSIONS_PATH}/{UNKNOWN_ID}", headers=ALICE, json={"title": "Renamed"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"


def test_rename_session_rejects_malformed_id(api_client: TestClient) -> None:
    response = api_client.patch(
        f"{SESSIONS_PATH}/not-an-id", headers=ALICE, json={"title": "Renamed"}
    )

    assert response.status_code == 422
    assert response.json()["details"][0]["loc"] == ["path", "session_id"]


def test_delete_session_removes_it(api_client: TestClient) -> None:
    session = create_session(api_client)

    response = api_client.delete(f"{SESSIONS_PATH}/{session['session_id']}", headers=ALICE)

    assert response.status_code == 204
    assert response.content == b""
    assert _titles(api_client) == []


def test_delete_session_twice_returns_no_content(api_client: TestClient) -> None:
    path = f"{SESSIONS_PATH}/{create_session(api_client)['session_id']}"
    api_client.delete(path, headers=ALICE)

    assert api_client.delete(path, headers=ALICE).status_code == 204


def test_delete_other_users_session_leaves_it(api_client: TestClient) -> None:
    session = create_session(api_client, title="Mine")

    response = api_client.delete(f"{SESSIONS_PATH}/{session['session_id']}", headers=BOB)

    assert response.status_code == 204
    assert _titles(api_client) == ["Mine"]


def test_list_messages_of_new_session_is_empty(api_client: TestClient) -> None:
    session = create_session(api_client)

    response = api_client.get(f"{SESSIONS_PATH}/{session['session_id']}/messages", headers=ALICE)

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


def test_list_messages_returns_stored_messages(
    api_client: TestClient, messages: DynamoDBMessageRepository
) -> None:
    session = create_session(api_client)
    message = MessageRecord(
        session_id=session["session_id"],
        message_id=str(ULID.from_datetime(WRITTEN_AT)),
        role=MessageRole.USER,
        content="Hello",
        created_at=WRITTEN_AT,
    )
    anyio.run(messages.add, message)

    response = api_client.get(f"{SESSIONS_PATH}/{session['session_id']}/messages", headers=ALICE)

    assert response.json() == {
        "items": [
            {
                "message_id": message.message_id,
                "role": "user",
                "content": "Hello",
                "created_at": "2026-11-06T12:00:00Z",
            }
        ],
        "next_cursor": None,
    }


def test_list_messages_of_other_users_session_returns_not_found(api_client: TestClient) -> None:
    session = create_session(api_client)

    response = api_client.get(f"{SESSIONS_PATH}/{session['session_id']}/messages", headers=BOB)

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"
