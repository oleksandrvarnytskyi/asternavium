# SPDX-License-Identifier: AGPL-3.0-or-later
"""Repository interfaces for the app table; services depend on these, not on DynamoDB.

Every method may raise :class:`~app.core.errors.StorageUnavailableError` when the database
fails; other errors are listed per method.
"""

from datetime import datetime
from typing import Protocol

from app.repositories.records import (
    MessageRecord,
    Page,
    PersonRecord,
    ProfileRecord,
    SessionRecord,
)


class ProfileRepository(Protocol):
    """Profiles, one per user."""

    async def get(self, user_id: str) -> ProfileRecord | None:
        """Return the user's profile, or ``None`` if none was saved."""
        ...

    async def put(self, profile: ProfileRecord) -> None:
        """Create or replace the user's profile."""
        ...

    async def delete(self, user_id: str) -> None:
        """Delete the user's profile; does nothing if there is none."""
        ...


class PersonRepository(Protocol):
    """Persons of a user, always addressed through their owner."""

    async def create(self, person: PersonRecord) -> None:
        """Store a new person.

        :raises ValueError: If a person with this ID already exists for the user; a ULID
            collision, so a programming error.
        """
        ...

    async def get(self, user_id: str, person_id: str) -> PersonRecord | None:
        """Return the person, or ``None`` if the user has no person with this ID."""
        ...

    async def list_page(
        self, user_id: str, *, limit: int, cursor: str | None
    ) -> Page[PersonRecord]:
        """Return the user's persons, newest first.

        :param limit: Maximum persons on the page; positive.
        :param cursor: ``next_cursor`` of the previous page, or ``None`` for the first page.
        :raises InvalidCursorError: If ``cursor`` was not issued for this list.
        """
        ...

    async def replace(self, person: PersonRecord) -> None:
        """Overwrite an existing person.

        :raises PersonNotFoundError: If the user has no person with this ID, e.g. it was
            deleted meanwhile.
        """
        ...

    async def delete(self, user_id: str, person_id: str) -> None:
        """Delete the person; does nothing if it does not exist."""
        ...


class SessionRepository(Protocol):
    """Chat sessions, always addressed through their owner, so ownership is part of every key."""

    async def create(self, session: SessionRecord) -> None:
        """Store a new session.

        :raises ValueError: If a session with this ID already exists for the user; a ULID
            collision, so a programming error.
        """
        ...

    async def get(self, user_id: str, session_id: str) -> SessionRecord | None:
        """Return the session, or ``None`` if the user has no session with this ID."""
        ...

    async def list_page(
        self, user_id: str, *, limit: int, cursor: str | None
    ) -> Page[SessionRecord]:
        """Return the user's sessions, newest first.

        :param limit: Maximum sessions on the page; positive.
        :param cursor: ``next_cursor`` of the previous page, or ``None`` for the first page.
        :raises InvalidCursorError: If ``cursor`` was not issued for this list.
        """
        ...

    async def rename(
        self, user_id: str, session_id: str, *, title: str, updated_at: datetime
    ) -> SessionRecord:
        """Set a session's title.

        :returns: The renamed session.
        :raises SessionNotFoundError: If the user has no session with this ID.
        """
        ...

    async def delete(self, user_id: str, session_id: str) -> None:
        """Delete the session record, not its messages; does nothing if it does not exist."""
        ...


class MessageRepository(Protocol):
    """Messages of a session; callers check that the caller owns the session first."""

    async def add(self, message: MessageRecord) -> None:
        """Store a new message.

        :raises ValueError: If a message with this ID already exists in the session.
        """
        ...

    async def list_page(
        self, session_id: str, *, limit: int, cursor: str | None
    ) -> Page[MessageRecord]:
        """Return the session's messages, newest first.

        :param limit: Maximum messages on the page; positive.
        :param cursor: ``next_cursor`` of the previous page, or ``None`` for the first page.
        :raises InvalidCursorError: If ``cursor`` was not issued for this list.
        """
        ...

    async def delete_all(self, session_id: str) -> None:
        """Delete every message of the session; safe to repeat after a partial failure."""
        ...
