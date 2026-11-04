# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI dependencies resolved from the application's composition root."""

import re
from typing import Annotated, Final

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from app.core.config import Environment, Settings
from app.core.errors import UnauthenticatedError
from app.core.identity import Principal

DEV_USER_HEADER: Final = "X-Dev-User"
# The ID ends up in DynamoDB keys, so only a small safe alphabet is accepted.
_VALID_DEV_USER: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")

# auto_error=False: a missing header must produce the shared error model, not FastAPI's default.
_dev_user_scheme: Final = APIKeyHeader(
    name=DEV_USER_HEADER,
    scheme_name="DevUser",
    description="Development-only identity: any user ID of 1 to 64 letters, digits, - and _.",
    auto_error=False,
)


def get_settings(request: Request) -> Settings:
    """Return the settings the application was created with."""
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_current_user(
    settings: SettingsDep,
    dev_user: Annotated[str | None, Security(_dev_user_scheme)],
) -> Principal:
    """Resolve the caller from the ``X-Dev-User`` header.

    Stand-in for real authentication until Phase 5; the header is trusted only in ``dev``.

    :param dev_user: Raw header value, or ``None`` if absent.
    :raises UnauthenticatedError: Outside ``dev``, or if the header is missing or malformed.
    """
    if settings.environment is not Environment.DEV:
        raise UnauthenticatedError("Authentication is required.")
    if dev_user is None or not _VALID_DEV_USER.fullmatch(dev_user):
        raise UnauthenticatedError(
            f"Set the {DEV_USER_HEADER} header to 1-64 letters, digits, '-' or '_'."
        )
    return Principal(user_id=dev_user)


CurrentUserDep = Annotated[Principal, Depends(get_current_user)]
