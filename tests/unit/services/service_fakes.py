# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-memory fakes of the repository Protocols and a settable clock for service tests."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from app.core.errors import (
    PersonNotFoundError,
    SessionNotFoundError,
    StorageUnavailableError,
)
from app.repositories.records import (
    MessageRecord,
    Page,
    PersonRecord,
    ProfileRecord,
    SessionRecord,
)


def _page[T](records: Iterable[tuple[str, T]], *, limit: int, cursor: str | None) -> Page[T]:
    """Page ``(id, record)`` pairs newest first; the cursor is the last ID on the page."""
    newest_first = sorted(records, key=lambda pair: pair[0], reverse=True)
    remaining = [pair for pair in newest_first if cursor is None or pair[0] < cursor]
    page, rest = remaining[:limit], remaining[limit:]
    next_cursor = page[-1][0] if rest else None
    return Page(items=tuple(record for _, record in page), next_cursor=next_cursor)


class FakeClock:
    """Returns a fixed instant until a test moves it."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class InMemoryProfileRepository:
    def __init__(self) -> None:
        self.profiles: dict[str, ProfileRecord] = {}

    async def get(self, user_id: str) -> ProfileRecord | None:
        return self.profiles.get(user_id)

    async def put(self, profile: ProfileRecord) -> None:
        self.profiles[profile.user_id] = profile

    async def delete(self, user_id: str) -> None:
        self.profiles.pop(user_id, None)


class InMemoryPersonRepository:
    def __init__(self) -> None:
        self.persons: dict[tuple[str, str], PersonRecord] = {}

    async def create(self, person: PersonRecord) -> None:
        key = (person.user_id, person.person_id)
        if key in self.persons:
            msg = "person already exists"
            raise ValueError(msg)
        self.persons[key] = person

    async def get(self, user_id: str, person_id: str) -> PersonRecord | None:
        return self.persons.get((user_id, person_id))

    async def list_page(
        self, user_id: str, *, limit: int, cursor: str | None
    ) -> Page[PersonRecord]:
        own = ((p.person_id, p) for (owner, _), p in self.persons.items() if owner == user_id)
        return _page(own, limit=limit, cursor=cursor)

    async def replace(self, person: PersonRecord) -> None:
        key = (person.user_id, person.person_id)
        if key not in self.persons:
            msg = "Person not found."
            raise PersonNotFoundError(msg)
        self.persons[key] = person

    async def delete(self, user_id: str, person_id: str) -> None:
        self.persons.pop((user_id, person_id), None)


class InMemorySessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[tuple[str, str], SessionRecord] = {}

    async def create(self, session: SessionRecord) -> None:
        key = (session.user_id, session.session_id)
        if key in self.sessions:
            msg = "session already exists"
            raise ValueError(msg)
        self.sessions[key] = session

    async def get(self, user_id: str, session_id: str) -> SessionRecord | None:
        return self.sessions.get((user_id, session_id))

    async def list_page(
        self, user_id: str, *, limit: int, cursor: str | None
    ) -> Page[SessionRecord]:
        own = ((s.session_id, s) for (owner, _), s in self.sessions.items() if owner == user_id)
        return _page(own, limit=limit, cursor=cursor)

    async def rename(
        self, user_id: str, session_id: str, *, title: str, updated_at: datetime
    ) -> SessionRecord:
        session = self.sessions.get((user_id, session_id))
        if session is None:
            msg = "Session not found."
            raise SessionNotFoundError(msg)
        renamed = SessionRecord(
            user_id=session.user_id,
            session_id=session.session_id,
            title=title,
            module=session.module,
            message_count=session.message_count,
            created_at=session.created_at,
            updated_at=updated_at,
        )
        self.sessions[(user_id, session_id)] = renamed
        return renamed

    async def delete(self, user_id: str, session_id: str) -> None:
        self.sessions.pop((user_id, session_id), None)


class InMemoryMessageRepository:
    """Message fake; ``delete_all`` fails once for each session ID in ``fail_delete_all_once``."""

    def __init__(self) -> None:
        self.messages: dict[str, dict[str, MessageRecord]] = {}
        self.fail_delete_all_once: set[str] = set()

    async def add(self, message: MessageRecord) -> None:
        session_messages = self.messages.setdefault(message.session_id, {})
        if message.message_id in session_messages:
            msg = "message already exists"
            raise ValueError(msg)
        session_messages[message.message_id] = message

    async def list_page(
        self, session_id: str, *, limit: int, cursor: str | None
    ) -> Page[MessageRecord]:
        records = self.messages.get(session_id, {}).items()
        return _page(records, limit=limit, cursor=cursor)

    async def delete_all(self, session_id: str) -> None:
        if session_id in self.fail_delete_all_once:
            self.fail_delete_all_once.remove(session_id)
            msg = "Storage is unavailable."
            raise StorageUnavailableError(msg)
        self.messages.pop(session_id, None)

    def count(self, session_id: str) -> int:
        return len(self.messages.get(session_id, {}))
