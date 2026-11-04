# SPDX-License-Identifier: AGPL-3.0-or-later
from fastapi.testclient import TestClient

from app import __version__
from app.core.config import Environment, Settings
from app.core.request_context import REQUEST_ID_HEADER
from app.main import create_app
from app.repositories.dynamodb import create_dynamodb_client


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_about_returns_build_and_source_info(client: TestClient, settings: Settings) -> None:
    response = client.get("/v1/about")

    assert response.status_code == 200
    assert response.json() == {
        "version": __version__,
        "commit_sha": settings.commit_sha,
        "source_url": str(settings.source_url),
        "license": "AGPL-3.0-or-later",
    }


def test_docs_are_served_in_dev(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200


def test_docs_are_disabled_in_prod(settings: Settings) -> None:
    prod_settings = settings.model_copy(update={"environment": Environment.PROD})
    client = TestClient(create_app(prod_settings))

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_response_reuses_valid_incoming_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={REQUEST_ID_HEADER: "req-123"})

    assert response.headers[REQUEST_ID_HEADER] == "req-123"


def test_response_replaces_malformed_incoming_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={REQUEST_ID_HEADER: "bad id!"})

    assert response.headers[REQUEST_ID_HEADER] != "bad id!"
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


def test_create_app_builds_dynamodb_client_from_settings(settings: Settings) -> None:
    app = create_app(settings)

    assert app.state.dynamodb_client.meta.region_name == settings.aws_region


def test_create_app_uses_injected_dynamodb_client(settings: Settings) -> None:
    injected = create_dynamodb_client(settings)

    app = create_app(settings, dynamodb_client=injected)

    assert app.state.dynamodb_client is injected
