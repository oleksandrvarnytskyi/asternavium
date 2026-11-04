# SPDX-License-Identifier: AGPL-3.0-or-later
"""Domain exception root and the HTTP handlers that render the shared error model."""

import logging
from http import HTTPStatus
from typing import ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import REQUEST_ID_HEADER, get_request_id
from app.schemas.errors import ErrorResponse, FieldError

logger = logging.getLogger(__name__)


class BaseAppError(Exception):
    """Root of all domain errors.

    Subclasses set ``code`` and ``http_status``. The message is returned to clients, so it
    must be actionable and must never contain personal data.
    """

    code: ClassVar[str] = "app_error"
    http_status: ClassVar[HTTPStatus] = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnauthenticatedError(BaseAppError):
    """The request carries no valid identity."""

    code: ClassVar[str] = "unauthenticated"
    http_status: ClassVar[HTTPStatus] = HTTPStatus.UNAUTHORIZED


def _error_response(status: HTTPStatus, body: ErrorResponse) -> JSONResponse:
    headers = {REQUEST_ID_HEADER: body.request_id} if body.request_id else None
    return JSONResponse(
        status_code=status, content=body.model_dump(exclude_none=True), headers=headers
    )


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BaseAppError)  # noqa: S101 - narrows the type for the registered class
    logger.warning("Domain error %s", exc.code)
    body = ErrorResponse(code=exc.code, message=exc.message, request_id=get_request_id())
    return _error_response(exc.http_status, body)


async def _handle_http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101 - narrows the registered type
    status = HTTPStatus(exc.status_code)
    body = ErrorResponse(
        code=status.name.lower(),
        message=exc.detail if isinstance(exc.detail, str) else status.phrase,
        request_id=get_request_id(),
    )
    return _error_response(status, body)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    """Report field locations and messages only; never echo the submitted input."""
    assert isinstance(exc, RequestValidationError)  # noqa: S101 - narrows the registered type
    details = [
        FieldError(loc=[str(part) for part in error["loc"]], msg=error["msg"])
        for error in exc.errors()
    ]
    body = ErrorResponse(
        code="validation_error",
        message="Request validation failed.",
        request_id=get_request_id(),
        details=details,
    )
    return _error_response(HTTPStatus.UNPROCESSABLE_CONTENT, body)


async def _handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error", exc_info=exc)
    body = ErrorResponse(
        code="internal_error", message="Internal server error.", request_id=get_request_id()
    )
    return _error_response(HTTPStatus.INTERNAL_SERVER_ERROR, body)


def register_error_handlers(app: FastAPI) -> None:
    """Install handlers so every error response follows :class:`ErrorResponse`."""
    app.add_exception_handler(BaseAppError, _handle_app_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
