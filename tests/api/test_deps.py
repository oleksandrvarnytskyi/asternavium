# SPDX-License-Identifier: AGPL-3.0-or-later
from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import DEV_USER_HEADER, CurrentUserDep
from app.core.config import Environment, Settings

PROBE_PATH = "/probe"
VALID_USER = "alice"


def _create_probe_app(make_app: Callable[[Settings], FastAPI], settings: Settings) -> FastAPI:
    """Build the real app plus one route that echoes the resolved user ID."""
    app = make_app(settings)

    @app.get(PROBE_PATH)
    async def probe(user: CurrentUserDep) -> dict[str, str]:
        return {"user_id": user.user_id}

    return app


@pytest.fixture
def probe_client(
    make_app: Callable[[Settings], FastAPI], settings: Settings
) -> Iterator[TestClient]:
    with TestClient(_create_probe_app(make_app, settings)) as test_client:
        yield test_client


@pytest.mark.parametrize("user_id", [VALID_USER, "a", "User_1-x", "x" * 64])
def test_get_current_user_accepts_valid_header_in_dev(
    probe_client: TestClient, user_id: str
) -> None:
    response = probe_client.get(PROBE_PATH, headers={DEV_USER_HEADER: user_id})

    assert response.status_code == 200
    assert response.json() == {"user_id": user_id}


def test_get_current_user_rejects_missing_header(probe_client: TestClient) -> None:
    response = probe_client.get(PROBE_PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


@pytest.mark.parametrize(
    "user_id",
    ["", "x" * 65, "alice bob", "alice@example.org", "USER#alice", "alice/../bob"],
)
def test_get_current_user_rejects_malformed_header(probe_client: TestClient, user_id: str) -> None:
    response = probe_client.get(PROBE_PATH, headers={DEV_USER_HEADER: user_id})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_get_current_user_error_does_not_echo_header_value(probe_client: TestClient) -> None:
    rejected = "not a valid user"

    response = probe_client.get(PROBE_PATH, headers={DEV_USER_HEADER: rejected})

    assert rejected not in response.text


def test_get_current_user_rejects_valid_header_outside_dev(
    make_app: Callable[[Settings], FastAPI], settings: Settings
) -> None:
    prod_settings = settings.model_copy(update={"environment": Environment.PROD})
    client = TestClient(_create_probe_app(make_app, prod_settings))

    response = client.get(PROBE_PATH, headers={DEV_USER_HEADER: VALID_USER})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_dev_user_header_is_declared_as_api_key_security_scheme(
    probe_client: TestClient,
) -> None:
    schema = probe_client.get("/openapi.json").json()

    scheme = schema["components"]["securitySchemes"]["DevUser"]
    assert (scheme["type"], scheme["in"], scheme["name"]) == ("apiKey", "header", DEV_USER_HEADER)
    assert schema["paths"][PROBE_PATH]["get"]["security"] == [{"DevUser": []}]
