# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build and source-code information required by the AGPL-3.0."""

from fastapi import APIRouter

from app import __version__
from app.api.deps import SettingsDep
from app.core.licensing import LICENSE_SPDX
from app.schemas.system import AboutResponse

router = APIRouter(tags=["system"])


@router.get("/about")
async def about(settings: SettingsDep) -> AboutResponse:
    """Return the running version, its commit and where to get the source."""
    return AboutResponse(
        version=__version__,
        commit_sha=settings.commit_sha,
        source_url=settings.source_url,
        license=LICENSE_SPDX,
    )
