# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application factory and composition root.

Run locally with ``uvicorn --factory app.main:create_app``.
"""

from typing import TYPE_CHECKING

from fastapi import FastAPI

from app import __version__
from app.api import health
from app.api.v1.router import router as v1_router
from app.core.config import Environment, Settings
from app.core.errors import register_error_handlers
from app.core.licensing import LICENSE_SPDX, LICENSE_URL
from app.core.logging import configure_logging
from app.core.request_context import RequestIdMiddleware
from app.repositories.dynamodb import create_dynamodb_client
from app.repositories.dynamodb_messages import DynamoDBMessageRepository
from app.repositories.dynamodb_persons import DynamoDBPersonRepository
from app.repositories.dynamodb_profiles import DynamoDBProfileRepository
from app.repositories.dynamodb_sessions import DynamoDBSessionRepository
from app.repositories.geonames import load_geonames_repository
from app.repositories.places import PlaceRepository
from app.services.accounts import AccountService
from app.services.persons import PersonService
from app.services.profiles import ProfileService
from app.services.sessions import SessionService

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient


def create_app(
    settings: Settings | None = None,
    *,
    dynamodb_client: "DynamoDBClient | None" = None,
    place_repository: PlaceRepository | None = None,
) -> FastAPI:
    """Build the FastAPI application.

    :param settings: Explicit settings, e.g. in tests; read from the environment if omitted.
    :param dynamodb_client: Explicit client, e.g. a moto-backed one in tests; built from
        settings if omitted.
    :param place_repository: Explicit places, e.g. a small synthetic set in tests; the bundled
        GeoNames snapshot is loaded if omitted (about three seconds).
    :returns: Configured application. API docs are served only in the ``dev`` environment.
    """
    resolved = settings if settings is not None else Settings()
    configure_logging(resolved.log_level)

    docs_enabled = resolved.environment is Environment.DEV
    app = FastAPI(
        title="AsterNavium API",
        version=__version__,
        license_info={"name": LICENSE_SPDX, "url": LICENSE_URL},
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = resolved
    client = dynamodb_client if dynamodb_client is not None else create_dynamodb_client(resolved)
    places = place_repository if place_repository is not None else load_geonames_repository()
    app.state.dynamodb_client = client
    app.state.place_repository = places
    _install_services(app, client, table_name=resolved.app_table_name, places=places)
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1_router)
    return app


def _install_services(
    app: FastAPI, client: "DynamoDBClient", *, table_name: str, places: PlaceRepository
) -> None:
    """Build the repositories and services once and keep them on ``app.state``."""
    profile_repository = DynamoDBProfileRepository(client, table_name)
    person_repository = DynamoDBPersonRepository(client, table_name)
    sessions = SessionService(
        DynamoDBSessionRepository(client, table_name),
        DynamoDBMessageRepository(client, table_name),
    )
    persons = PersonService(person_repository, profile_repository, places)
    profiles = ProfileService(profile_repository, person_repository)
    app.state.session_service = sessions
    app.state.person_service = persons
    app.state.profile_service = profiles
    app.state.account_service = AccountService(profiles, persons, sessions)
