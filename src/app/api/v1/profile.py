# SPDX-License-Identifier: AGPL-3.0-or-later
"""The caller's profile; read it back with GET /v1/me."""

from http import HTTPStatus

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, ProfileServiceDep
from app.api.responses import error_responses
from app.schemas.profile import ProfileRequest, ProfileResponse

router = APIRouter(
    prefix="/profile",
    tags=["me"],
    responses=error_responses(
        HTTPStatus.UNAUTHORIZED, HTTPStatus.UNPROCESSABLE_CONTENT, HTTPStatus.SERVICE_UNAVAILABLE
    ),
)


@router.put("", responses=error_responses(HTTPStatus.NOT_FOUND))
async def replace_profile(
    user: CurrentUserDep, profiles: ProfileServiceDep, body: ProfileRequest
) -> ProfileResponse:
    """Create or replace your profile.

    ``owner_person_id`` must name one of your persons (``404 person_not_found`` otherwise).
    """
    profile = await profiles.replace(
        user.user_id,
        locale=body.locale,
        traditions=frozenset(body.traditions),
        answer_depth=body.answer_depth,
        owner_person_id=body.owner_person_id,
    )
    return ProfileResponse.from_record(profile)
