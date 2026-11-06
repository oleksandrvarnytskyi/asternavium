# SPDX-License-Identifier: AGPL-3.0-or-later
"""Chat sessions of one user and their message history, with the ownership check."""

from typing import Final

from ulid import ULID

from app.core.clock import Clock, utc_now
from app.core.errors import SessionNotFoundError
from app.domain.chat import DEFAULT_SESSION_TITLE, ChatModule
from app.repositories.protocols import MessageRepository, SessionRepository
from app.repositories.records import MessageRecord, Page, SessionRecord

_NOT_FOUND_MESSAGE: Final = "Session not found."
# delete_all removes each page it reads, so it re-reads the first page until it is empty.
_DELETE_ALL_PAGE_SIZE: Final = 25


class SessionService:
    """Create, read, rename and delete a user's sessions.

    Every method takes the caller's user ID; a session of another user is reported exactly
    like a missing one, so session IDs reveal nothing about other users.
    """

    def __init__(
        self,
        sessions: SessionRepository,
        messages: MessageRepository,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._sessions = sessions
        self._messages = messages
        self._clock = clock

    async def create(
        self, user_id: str, *, module: ChatModule, title: str = DEFAULT_SESSION_TITLE
    ) -> SessionRecord:
        """Create an empty session.

        :param title: Display title; length is limited by the API schema.
        :returns: The new session; its ULID encodes the creation time.
        """
        now = self._clock()
        session = SessionRecord(
            user_id=user_id,
            session_id=str(ULID.from_datetime(now)),
            title=title,
            module=module,
            message_count=0,
            created_at=now,
            updated_at=now,
        )
        await self._sessions.create(session)
        return session

    async def list_page(
        self, user_id: str, *, limit: int, cursor: str | None
    ) -> Page[SessionRecord]:
        """Return the user's sessions, newest first.

        :param limit: Maximum sessions on the page; positive.
        :param cursor: ``next_cursor`` of the previous page, or ``None`` for the first page.
        :raises InvalidCursorError: If ``cursor`` was not issued for this list.
        """
        return await self._sessions.list_page(user_id, limit=limit, cursor=cursor)

    async def get(self, user_id: str, session_id: str) -> SessionRecord:
        """Return one of the user's sessions.

        :raises SessionNotFoundError: If the user has no session with this ID.
        """
        session = await self._sessions.get(user_id, session_id)
        if session is None:
            raise SessionNotFoundError(_NOT_FOUND_MESSAGE)
        return session

    async def rename(self, user_id: str, session_id: str, *, title: str) -> SessionRecord:
        """Set a session's title and its update time.

        :returns: The renamed session.
        :raises SessionNotFoundError: If the user has no session with this ID.
        """
        return await self._sessions.rename(
            user_id, session_id, title=title, updated_at=self._clock()
        )

    async def delete(self, user_id: str, session_id: str) -> None:
        """Delete a session and all its messages; does nothing if the user has no such session.

        Messages go first, so a retry after a partial failure still finds the session and
        finishes. The ownership check comes before any delete, because message keys hold only
        the session ID.
        """
        if await self._sessions.get(user_id, session_id) is None:
            return
        await self._delete_owned(user_id, session_id)

    async def delete_all(self, user_id: str) -> None:
        """Delete every session of the user with its messages; safe to repeat."""
        while True:
            page = await self._sessions.list_page(user_id, limit=_DELETE_ALL_PAGE_SIZE, cursor=None)
            if not page.items:
                return
            for session in page.items:
                await self._delete_owned(user_id, session.session_id)

    async def list_messages(
        self, user_id: str, session_id: str, *, limit: int, cursor: str | None
    ) -> Page[MessageRecord]:
        """Return a session's messages, newest first, after checking the user owns it.

        :param limit: Maximum messages on the page; positive.
        :param cursor: ``next_cursor`` of the previous page, or ``None`` for the first page.
        :raises SessionNotFoundError: If the user has no session with this ID.
        :raises InvalidCursorError: If ``cursor`` was not issued for this list.
        """
        await self.get(user_id, session_id)
        return await self._messages.list_page(session_id, limit=limit, cursor=cursor)

    async def _delete_owned(self, user_id: str, session_id: str) -> None:
        await self._messages.delete_all(session_id)
        await self._sessions.delete(user_id, session_id)
