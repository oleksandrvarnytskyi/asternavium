# SPDX-License-Identifier: AGPL-3.0-or-later
"""The current user's account."""

from http import HTTPStatus

from fastapi import APIRouter

from app.api.deps import AccountServiceDep, CurrentUserDep, ProfileServiceDep
from app.api.responses import error_responses
from app.schemas.profile import MeResponse, ProfileResponse

router = APIRouter(
    prefix="/me",
    tags=["me"],
    responses=error_responses(HTTPStatus.UNAUTHORIZED, HTTPStatus.SERVICE_UNAVAILABLE),
)


@router.get("")
async def get_me(user: CurrentUserDep, profiles: ProfileServiceDep) -> MeResponse:
    """Read your user ID and profile."""
    profile = await profiles.get(user.user_id)
    return MeResponse(
        user_id=user.user_id,
        profile=ProfileResponse.from_record(profile) if profile else None,
    )


@router.delete("", status_code=HTTPStatus.NO_CONTENT)
async def delete_me(user: CurrentUserDep, accounts: AccountServiceDep) -> None:
    """Delete your account: the profile, all persons, all sessions and their messages.

    Idempotent: if a deletion fails part-way, repeat it to finish.
    """
    await accounts.delete(user.user_id)
