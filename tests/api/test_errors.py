# SPDX-License-Identifier: AGPL-3.0-or-later
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import BaseAppError
from app.core.request_context import REQUEST_ID_HEADER
from app.main import create_app


class _NotFoundError(BaseAppError):
    code = "thing_not_found"
    http_status = HTTPStatus.NOT_FOUND


class _Payload(BaseModel):
    name: str


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    app = create_app(settings)

    @app.get("/domain-error")
    async def domain_error() -> None:
        raise _NotFoundError("Thing does not exist.")

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("boom")

    @app.post("/echo")
    async def echo(payload: _Payload) -> _Payload:
        return payload

    return app


def test_domain_error_uses_its_code_and_status(app: FastAPI) -> None:
    response = TestClient(app).get("/domain-error", headers={REQUEST_ID_HEADER: "r1"})

    assert response.status_code == 404
    assert response.json() == {
        "code": "thing_not_found",
        "message": "Thing does not exist.",
        "request_id": "r1",
    }


def test_unknown_route_returns_error_model(app: FastAPI) -> None:
    response = TestClient(app).get("/missing", headers={REQUEST_ID_HEADER: "r2"})

    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "message": "Not Found", "request_id": "r2"}


def test_validation_error_omits_submitted_input(app: FastAPI) -> None:
    response = TestClient(app).post("/echo", json={"name": 12345678})

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "validation_error"
    assert body["details"][0]["loc"] == ["body", "name"]
    assert "12345678" not in response.text


def test_unexpected_error_hides_internals(app: FastAPI) -> None:
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/crash", headers={REQUEST_ID_HEADER: "r3"})

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "Internal server error.",
        "request_id": "r3",
    }
    assert response.headers[REQUEST_ID_HEADER] == "r3"
    assert "boom" not in response.text
