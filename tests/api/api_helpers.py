# SPDX-License-Identifier: AGPL-3.0-or-later
"""Requests and payloads shared by the API tests.

All birth data here is synthetic; none of it belongs to a real person.
"""

from typing import Any, Final

from fastapi.testclient import TestClient
from ulid import ULID

from app.api.deps import DEV_USER_HEADER

ALICE: Final = {DEV_USER_HEADER: "alice"}
BOB: Final = {DEV_USER_HEADER: "bob"}
# Kyiv and Paris, Texas in conftest.TEST_PLACE_RECORDS.
KYIV: Final = "4"
PARIS_TEXAS: Final = "2"
BIRTH: Final[dict[str, Any]] = {"date": "1990-05-17", "time": "14:30", "place_id": KYIV}
# A well-formed ID that names nothing.
UNKNOWN_ID: Final = str(ULID())


def create_person(
    client: TestClient,
    headers: dict[str, str] = ALICE,
    *,
    label: str = "Me",
    birth: dict[str, Any] = BIRTH,
) -> dict[str, Any]:
    """Add a person and return the response body."""
    response = client.post("/v1/persons", headers=headers, json={"label": label, "birth": birth})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def create_session(
    client: TestClient, headers: dict[str, str] = ALICE, *, title: str | None = None
) -> dict[str, Any]:
    """Create a general session and return the response body."""
    payload: dict[str, Any] = {"module": "general"}
    if title is not None:
        payload["title"] = title
    response = client.post("/v1/sessions", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def save_profile(
    client: TestClient, headers: dict[str, str] = ALICE, **fields: Any
) -> dict[str, Any]:
    """Replace the profile with the given fields and return the response body."""
    response = client.put("/v1/profile", headers=headers, json=fields)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body
