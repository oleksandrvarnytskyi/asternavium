# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from app.core.config import Environment, Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Settings built without reading the process environment or ``.env``."""
    return Settings(
        _env_file=None,
        environment=Environment.DEV,
        source_url=HttpUrl("https://example.org/asternavium"),
        commit_sha="abc123",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
