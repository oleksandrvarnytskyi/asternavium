# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application factory and composition root.

Run locally with ``uvicorn --factory app.main:create_app``.
"""

from fastapi import FastAPI

from app import __version__
from app.api import health
from app.api.v1.router import router as v1_router
from app.core.config import Environment, Settings
from app.core.errors import register_error_handlers
from app.core.licensing import LICENSE_SPDX, LICENSE_URL
from app.core.logging import configure_logging
from app.core.request_context import RequestIdMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    :param settings: Explicit settings, e.g. in tests; read from the environment if omitted.
    :returns: Configured application. API docs are served only in the ``dev`` environment.
    """
    resolved = settings if settings is not None else Settings()
    configure_logging(resolved.log_level)

    docs_enabled = resolved.environment is Environment.DEV
    app = FastAPI(
        title="AsterAvium API",
        version=__version__,
        license_info={"name": LICENSE_SPDX, "url": LICENSE_URL},
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = resolved
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1_router)
    return app
