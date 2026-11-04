# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from mypy_boto3_dynamodb import DynamoDBClient
from pydantic import HttpUrl

from app.core.config import Environment, Settings
from app.main import create_app
from app.repositories.app_table import ensure_app_table
from app.repositories.dynamodb import create_dynamodb_client


@pytest.fixture(autouse=True)
def _fake_aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace any real AWS credentials, so no test can reach a real account."""
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


@pytest.fixture
def settings() -> Settings:
    """Settings for tests, built without reading the developer's ``.env``."""
    return Settings(
        _env_file=None,
        environment=Environment.DEV,
        source_url=HttpUrl("https://example.org/asternavium"),
        commit_sha="abc123",
        app_table_name="asternavium-test-table",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def mocked_aws() -> Iterator[None]:
    """Serve every AWS call from moto's in-memory backend for the duration of a test."""
    with mock_aws():
        yield


@pytest.fixture
def dynamodb_client(mocked_aws: None, settings: Settings) -> DynamoDBClient:
    """The app's DynamoDB client, built from settings and backed by moto."""
    return create_dynamodb_client(settings)


@pytest.fixture
def app_table(dynamodb_client: DynamoDBClient, settings: Settings) -> str:
    """Create the app table in moto from the app's table definition; return its name."""
    ensure_app_table(dynamodb_client, settings.app_table_name)
    return settings.app_table_name
