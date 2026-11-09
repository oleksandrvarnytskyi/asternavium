# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rules every ``/v1`` endpoint follows: authentication and documented error responses."""

from typing import Any

import pytest
from api_helpers import UNKNOWN_ID
from fastapi.testclient import TestClient

ERROR_SCHEMA_REF = "#/components/schemas/ErrorResponse"
# Every endpoint that acts for a user; /v1/about is public.
USER_ENDPOINTS = [
    ("GET", "/v1/places?query=par"),
    ("GET", "/v1/me"),
    ("DELETE", "/v1/me"),
    ("PUT", "/v1/profile"),
    ("POST", "/v1/persons"),
    ("GET", "/v1/persons"),
    ("GET", f"/v1/persons/{UNKNOWN_ID}"),
    ("PUT", f"/v1/persons/{UNKNOWN_ID}"),
    ("DELETE", f"/v1/persons/{UNKNOWN_ID}"),
    ("POST", "/v1/sessions"),
    ("GET", "/v1/sessions"),
    ("PATCH", f"/v1/sessions/{UNKNOWN_ID}"),
    ("DELETE", f"/v1/sessions/{UNKNOWN_ID}"),
    ("GET", f"/v1/sessions/{UNKNOWN_ID}/messages"),
]


def _user_operations(client: TestClient) -> list[tuple[str, dict[str, Any]]]:
    paths = client.get("/openapi.json").json()["paths"]
    return [
        (f"{method.upper()} {path}", operation)
        for path, operations in paths.items()
        if path.startswith("/v1/") and path != "/v1/about"
        for method, operation in operations.items()
    ]


@pytest.mark.parametrize(("method", "path"), USER_ENDPOINTS)
def test_endpoint_without_identity_returns_unauthenticated(
    api_client: TestClient, method: str, path: str
) -> None:
    response = api_client.request(method, path, json={})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_every_user_endpoint_is_covered_by_the_identity_test(api_client: TestClient) -> None:
    documented = {name for name, _ in _user_operations(api_client)}

    assert len(documented) == len(USER_ENDPOINTS)


def test_every_user_endpoint_documents_errors_with_the_shared_model(
    api_client: TestClient,
) -> None:
    for name, operation in _user_operations(api_client):
        errors = {
            status: body for status, body in operation["responses"].items() if status >= "400"
        }
        assert "401" in errors, name
        for status, body in errors.items():
            schema = body["content"]["application/json"]["schema"]
            assert schema == {"$ref": ERROR_SCHEMA_REF}, (name, status)


def test_openapi_has_no_default_validation_error_schema(api_client: TestClient) -> None:
    schemas = api_client.get("/openapi.json").json()["components"]["schemas"]

    assert "HTTPValidationError" not in schemas
