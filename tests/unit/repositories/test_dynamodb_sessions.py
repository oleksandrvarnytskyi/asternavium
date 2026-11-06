# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import UTC, datetime, timedelta

import pytest
from ulid import ULID

from app.core.errors import InvalidCursorError, SessionNotFoundError
from app.domain.chat import ChatModule
from app.repositories.dynamodb_sessions import DynamoDBSessionRepository
from app.repositories.records import SessionRecord

pytestmark = pytest.mark.anyio

START = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
RENAMED_AT = START + timedelta(hours=1)


def _session(user_id: str = "alice", *, minute: int = 0) -> SessionRecord:
    """Build a session created ``minute`` minutes after START; later minutes sort newer."""
    created = START + timedelta(minutes=minute)
    return SessionRecord(
        user_id=user_id,
        session_id=str(ULID.from_datetime(created)),
        title=f"Chat {minute}",
        module=ChatModule.JYOTISHA,
        message_count=0,
        created_at=created,
        updated_at=created,
    )


async def _create_sessions(
    sessions: DynamoDBSessionRepository, count: int, user_id: str = "alice"
) -> list[SessionRecord]:
    created = [_session(user_id, minute=minute) for minute in range(count)]
    for session in created:
        await sessions.create(session)
    return created


async def _list_all_titles(sessions: DynamoDBSessionRepository, *, limit: int) -> list[list[str]]:
    """Follow cursors to the end and return the titles on each page."""
    pages: list[list[str]] = []
    cursor: str | None = None
    while True:
        page = await sessions.list_page("alice", limit=limit, cursor=cursor)
        pages.append([session.title for session in page.items])
        if page.next_cursor is None:
            return pages
        cursor = page.next_cursor


async def test_create_then_get_returns_session(sessions: DynamoDBSessionRepository) -> None:
    session = _session()

    await sessions.create(session)

    assert await sessions.get("alice", session.session_id) == session


async def test_create_rejects_existing_session_id(sessions: DynamoDBSessionRepository) -> None:
    session = _session()
    await sessions.create(session)

    with pytest.raises(ValueError, match="already exists"):
        await sessions.create(session)


async def test_get_returns_none_for_missing_session(sessions: DynamoDBSessionRepository) -> None:
    assert await sessions.get("alice", str(ULID())) is None


async def test_get_returns_none_for_other_users_session(
    sessions: DynamoDBSessionRepository,
) -> None:
    session = _session("alice")
    await sessions.create(session)

    assert await sessions.get("bob", session.session_id) is None


async def test_list_page_returns_newest_first(sessions: DynamoDBSessionRepository) -> None:
    await _create_sessions(sessions, 3)

    page = await sessions.list_page("alice", limit=10, cursor=None)

    assert [session.title for session in page.items] == ["Chat 2", "Chat 1", "Chat 0"]
    assert page.next_cursor is None


async def test_list_page_follows_cursors_across_pages(sessions: DynamoDBSessionRepository) -> None:
    await _create_sessions(sessions, 5)

    pages = await _list_all_titles(sessions, limit=2)

    assert pages == [["Chat 4", "Chat 3"], ["Chat 2", "Chat 1"], ["Chat 0"]]


async def test_list_page_has_no_empty_last_page(sessions: DynamoDBSessionRepository) -> None:
    await _create_sessions(sessions, 4)

    pages = await _list_all_titles(sessions, limit=2)

    assert pages == [["Chat 3", "Chat 2"], ["Chat 1", "Chat 0"]]


async def test_list_page_of_user_without_sessions_is_empty(
    sessions: DynamoDBSessionRepository,
) -> None:
    page = await sessions.list_page("alice", limit=10, cursor=None)

    assert page.items == ()
    assert page.next_cursor is None


async def test_list_page_shows_only_own_sessions(sessions: DynamoDBSessionRepository) -> None:
    await _create_sessions(sessions, 2, user_id="alice")
    await _create_sessions(sessions, 3, user_id="bob")

    page = await sessions.list_page("alice", limit=10, cursor=None)

    assert {session.user_id for session in page.items} == {"alice"}
    assert len(page.items) == 2


async def test_list_page_cursor_cannot_reach_other_users_sessions(
    sessions: DynamoDBSessionRepository,
) -> None:
    await _create_sessions(sessions, 3, user_id="bob")
    bobs_cursor = (await sessions.list_page("bob", limit=1, cursor=None)).next_cursor

    page = await sessions.list_page("alice", limit=10, cursor=bobs_cursor)

    assert page.items == ()


async def test_list_page_rejects_malformed_cursor(sessions: DynamoDBSessionRepository) -> None:
    with pytest.raises(InvalidCursorError):
        await sessions.list_page("alice", limit=10, cursor="not-a-cursor")


async def test_rename_updates_title_and_timestamp(sessions: DynamoDBSessionRepository) -> None:
    session = _session()
    await sessions.create(session)

    renamed = await sessions.rename(
        "alice", session.session_id, title="Moon questions", updated_at=RENAMED_AT
    )

    assert (renamed.title, renamed.updated_at, renamed.created_at) == (
        "Moon questions",
        RENAMED_AT,
        session.created_at,
    )
    assert await sessions.get("alice", session.session_id) == renamed


async def test_rename_missing_session_raises_not_found(
    sessions: DynamoDBSessionRepository,
) -> None:
    missing_id = str(ULID())

    with pytest.raises(SessionNotFoundError):
        await sessions.rename("alice", missing_id, title="x", updated_at=RENAMED_AT)

    assert await sessions.get("alice", missing_id) is None


async def test_rename_other_users_session_raises_not_found(
    sessions: DynamoDBSessionRepository,
) -> None:
    session = _session("alice")
    await sessions.create(session)

    with pytest.raises(SessionNotFoundError):
        await sessions.rename("bob", session.session_id, title="Hijacked", updated_at=RENAMED_AT)

    assert await sessions.get("alice", session.session_id) == session


async def test_delete_removes_only_that_session(sessions: DynamoDBSessionRepository) -> None:
    first, second = await _create_sessions(sessions, 2)

    await sessions.delete("alice", first.session_id)

    assert await sessions.get("alice", first.session_id) is None
    assert await sessions.get("alice", second.session_id) == second


async def test_delete_is_idempotent(sessions: DynamoDBSessionRepository) -> None:
    session = _session()
    await sessions.create(session)

    await sessions.delete("alice", session.session_id)
    await sessions.delete("alice", session.session_id)

    assert await sessions.get("alice", session.session_id) is None


async def test_delete_of_other_users_session_leaves_it(
    sessions: DynamoDBSessionRepository,
) -> None:
    session = _session("alice")
    await sessions.create(session)

    await sessions.delete("bob", session.session_id)

    assert await sessions.get("alice", session.session_id) == session
