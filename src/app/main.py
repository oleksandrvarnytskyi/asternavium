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
from app.repositories.geonames import load_geonames_repository
from app.repositories.places import PlaceRepository

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
    app.state.dynamodb_client = (
        dynamodb_client if dynamodb_client is not None else create_dynamodb_client(resolved)
    )
    app.state.place_repository = (
        place_repository if place_repository is not None else load_geonames_repository()
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1_router)
    return app
