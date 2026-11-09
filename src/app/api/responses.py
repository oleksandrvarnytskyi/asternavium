# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAPI descriptions of the error responses an endpoint can return."""

from http import HTTPStatus
from typing import Any

from app.schemas.errors import ErrorResponse


def error_responses(*statuses: HTTPStatus) -> dict[int | str, dict[str, Any]]:
    """Document each status as returning the shared error model.

    Listing ``422`` also replaces FastAPI's default validation error schema, which this API
    never returns.

    :returns: Value for the ``responses`` argument of a router or route.
    """
    return {
        status.value: {"model": ErrorResponse, "description": status.phrase} for status in statuses
    }
