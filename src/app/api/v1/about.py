"""Build information and third-party data credits."""

from fastapi import APIRouter

from app import __version__
from app.api.deps import SettingsDep
from app.core.attributions import DATA_ATTRIBUTIONS
from app.schemas.system import AboutResponse, DataAttributionResponse

router = APIRouter(tags=["system"])


@router.get("/about")
async def about(settings: SettingsDep) -> AboutResponse:
    """Return the running version, its commit and the credits for third-party data."""
    return AboutResponse(
        version=__version__,
        commit_sha=settings.commit_sha,
        attributions=[
            DataAttributionResponse.model_validate(item, from_attributes=True)
            for item in DATA_ATTRIBUTIONS
        ],
    )
