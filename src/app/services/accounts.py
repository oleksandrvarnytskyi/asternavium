# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deletion of a whole account."""

from app.services.profiles import ProfileService
from app.services.sessions import SessionService


class AccountService:
    """Operations on a user's account as a whole."""

    def __init__(self, profiles: ProfileService, sessions: SessionService) -> None:
        self._profiles = profiles
        self._sessions = sessions

    async def delete(self, user_id: str) -> None:
        """Delete every session, message and the profile of the user.

        Idempotent: each step deletes only what is still there, so a retry after a partial
        failure finishes the job.
        """
        await self._sessions.delete_all(user_id)
        await self._profiles.delete(user_id)
