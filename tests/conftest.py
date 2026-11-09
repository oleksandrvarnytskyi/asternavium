# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared fixtures."""

from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from moto import mock_aws
from mypy_boto3_dynamodb import DynamoDBClient
from pydantic import HttpUrl

from app.core.config import Environment, Settings
from app.main import create_app
from app.repositories.app_table import ensure_app_table
from app.repositories.dynamodb import create_dynamodb_client
from app.repositories.dynamodb_messages import DynamoDBMessageRepository
from app.repositories.dynamodb_persons import DynamoDBPersonRepository
from app.repositories.dynamodb_profiles import DynamoDBProfileRepository
from app.repositories.dynamodb_sessions import DynamoDBSessionRepository
from app.repositories.geonames import (
    GeoNamesPlaceRepository,
    GeoNamesRecord,
    load_geonames_repository,
)
from app.repositories.places import Place

type AppFactory = Callable[[Settings], FastAPI]

TEST_DATASET_VERSION = "2000-01-01"
# Synthetic places: real names for readable tests, invented figures. Warsaw's nickname makes it
# an alternate-name match for "par", which must rank below every main-name match.
TEST_PLACE_RECORDS = (
    GeoNamesRecord(
        place=Place(
            place_id="1",
            name="Paris",
            region="Île-de-France",
            country="France",
            latitude=48.85,
            longitude=2.35,
            population=2_000_000,
            timezone="Europe/Paris",
        ),
        main_names=("Paris", "Paris"),
        alternate_names=("Parigi", "Париж"),
    ),
    GeoNamesRecord(
        place=Place(
            place_id="2",
            name="Paris",
            region="Texas",
            country="United States",
            latitude=33.66,
            longitude=-95.56,
            population=25_000,
            timezone="America/Chicago",
        ),
        main_names=("Paris", "Paris"),
        alternate_names=(),
    ),
    GeoNamesRecord(
        place=Place(
            place_id="3",
            name="Warsaw",
            region="Mazovia",
            country="Poland",
            latitude=52.23,
            longitude=21.01,
            population=1_700_000,
            timezone="Europe/Warsaw",
        ),
        main_names=("Warsaw", "Warsaw"),
        alternate_names=("Warszawa", "Paris of the North"),
    ),
    GeoNamesRecord(
        place=Place(
            place_id="4",
            name="Kyiv",
            region=None,
            country="Ukraine",
            latitude=50.45,
            longitude=30.52,
            population=3_000_000,
            timezone="Europe/Kyiv",
        ),
        main_names=("Kyiv", "Kyiv"),
        alternate_names=("Київ", "Kiev"),
    ),
)


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
def place_repository() -> GeoNamesPlaceRepository:
    """A few synthetic places; tests use it instead of the slow-to-load bundled snapshot."""
    return GeoNamesPlaceRepository(TEST_PLACE_RECORDS, dataset_version=TEST_DATASET_VERSION)


@pytest.fixture(scope="session")
def bundled_places() -> GeoNamesPlaceRepository:
    """The real bundled GeoNames snapshot, loaded once per test run for smoke tests."""
    return load_geonames_repository()


@pytest.fixture
def make_app(place_repository: GeoNamesPlaceRepository) -> AppFactory:
    """Build the app with the synthetic places, so no test pays for loading the snapshot."""

    def factory(settings: Settings) -> FastAPI:
        return create_app(settings, place_repository=place_repository)

    return factory


@pytest.fixture
def client(make_app: AppFactory, settings: Settings) -> Iterator[TestClient]:
    with TestClient(make_app(settings)) as test_client:
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


@pytest.fixture
def anyio_backend() -> str:
    """Run ``@pytest.mark.anyio`` tests on asyncio, the loop the app runs on."""
    return "asyncio"


@pytest.fixture
def profiles(dynamodb_client: DynamoDBClient, app_table: str) -> DynamoDBProfileRepository:
    """Profile repository on the moto-backed app table."""
    return DynamoDBProfileRepository(dynamodb_client, app_table)


@pytest.fixture
def persons(dynamodb_client: DynamoDBClient, app_table: str) -> DynamoDBPersonRepository:
    """Person repository on the moto-backed app table."""
    return DynamoDBPersonRepository(dynamodb_client, app_table)


@pytest.fixture
def sessions(dynamodb_client: DynamoDBClient, app_table: str) -> DynamoDBSessionRepository:
    """Session repository on the moto-backed app table."""
    return DynamoDBSessionRepository(dynamodb_client, app_table)


@pytest.fixture
def messages(dynamodb_client: DynamoDBClient, app_table: str) -> DynamoDBMessageRepository:
    """Message repository on the moto-backed app table."""
    return DynamoDBMessageRepository(dynamodb_client, app_table)


@pytest.fixture
def api_client(
    settings: Settings,
    dynamodb_client: DynamoDBClient,
    app_table: str,
    place_repository: GeoNamesPlaceRepository,
) -> Iterator[TestClient]:
    """The app on the moto-backed app table, with the synthetic places."""
    assert app_table == settings.app_table_name
    app = create_app(settings, dynamodb_client=dynamodb_client, place_repository=place_repository)
    with TestClient(app) as test_client:
        yield test_client
