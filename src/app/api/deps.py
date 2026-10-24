# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI dependencies resolved from the application's composition root."""

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings


def get_settings(request: Request) -> Settings:
    """Return the settings the application was created with."""
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]
