# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import UTC, datetime, timedelta

import pytest
from service_fakes import (
    FakeClock,
    InMemoryMessageRepository,
    InMemorySessionRepository,
)
from ulid import ULID

from app.core.errors import SessionNotFoundError, StorageUnavailableError
from app.domain.chat import DEFAULT_SESSION_TITLE, ChatModule, MessageRole
from app.repositories.records import MessageRecord
from app.services.sessions import SessionService

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
# More than one page of delete_all, so it must loop.
MANY_SESSIONS = 30


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def session_repository() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def message_repository() -> InMemoryMessageRepository:
    return InMemoryMessageRepository()


@pytest.fixture
def service(
    session_repository: InMemorySessionRepository,
    message_repository: InMemoryMessageRepository,
    clock: FakeClock,
) -> SessionService:
    return SessionService(session_repository, message_repository, clock=clock)


async def _add_messages(messages: InMemoryMessageRepository, session_id: str, count: int) -> None:
    for second in range(count):
        created = NOW + timedelta(seconds=second)
        await messages.add(
            MessageRecord(
                session_id=session_id,
                message_id=str(ULID.from_datetime(created)),
                role=MessageRole.USER,
                content=f"Message {second}",
                created_at=created,
            )
        )


async def test_create_builds_empty_session_at_current_time(service: SessionService) -> None:
    session = await service.create("alice", module=ChatModule.JYOTISHA)

    assert (session.user_id, session.title, session.module, session.message_count) == (
        "alice",
        DEFAULT_SESSION_TITLE,
        ChatModule.JYOTISHA,
        0,
    )
    assert session.created_at == session.updated_at == NOW
    assert ULID.from_str(session.session_id).datetime == NOW


async def test_create_stores_session_with_given_title(service: SessionService) -> None:
    session = await service.create("alice", module=ChatModule.GENERAL, title="Moon questions")

    assert await service.get("alice", session.session_id) == session
    assert session.title == "Moon questions"


async def test_list_page_returns_newest_first(service: SessionService, clock: FakeClock) -> None:
    for title in ("First", "Second", "Third"):
        await service.create("alice", module=ChatModule.GENERAL, title=title)
        clock.advance(timedelta(minutes=1))

    first = await service.list_page("alice", limit=2, cursor=None)
    second = await service.list_page("alice", limit=2, cursor=first.next_cursor)

    assert [session.title for session in first.items] == ["Third", "Second"]
    assert [session.title for session in second.items] == ["First"]
    assert second.next_cursor is None


async def test_get_missing_session_raises_not_found(service: SessionService) -> None:
    with pytest.raises(SessionNotFoundError):
        await service.get("alice", str(ULID()))


async def test_get_other_users_session_raises_not_found(service: SessionService) -> None:
    session = await service.create("alice", module=ChatModule.GENERAL)

    with pytest.raises(SessionNotFoundError):
        await service.get("bob", session.session_id)


async def test_rename_sets_title_and_update_time(service: SessionService, clock: FakeClock) -> None:
    session = await service.create("alice", module=ChatModule.GENERAL)
    clock.advance(timedelta(hours=1))

    renamed = await service.rename("alice", session.session_id, title="Moon questions")

    assert (renamed.title, renamed.created_at, renamed.updated_at) == (
        "Moon questions",
        NOW,
        NOW + timedelta(hours=1),
    )
    assert await service.get("alice", session.session_id) == renamed


async def test_rename_other_users_session_raises_not_found(service: SessionService) -> None:
    session = await service.create("alice", module=ChatModule.GENERAL)

    with pytest.raises(SessionNotFoundError):
        await service.rename("bob", session.session_id, title="Hijacked")

    assert (await service.get("alice", session.session_id)).title == DEFAULT_SESSION_TITLE


async def test_delete_removes_session_and_its_messages(
    service: SessionService, message_repository: InMemoryMessageRepository
) -> None:
    session = await service.create("alice", module=ChatModule.GENERAL)
    await _add_messages(message_repository, session.session_id, 3)

    await service.delete("alice", session.session_id)

    with pytest.raises(SessionNotFoundError):
        await service.get("alice", session.session_id)
    assert message_repository.count(session.session_id) == 0


async def test_delete_leaves_other_sessions(
    service: SessionService, message_repository: InMemoryMessageRepository
) -> None:
    deleted = await service.create("alice", module=ChatModule.GENERAL)
    kept = await service.create("alice", module=ChatModule.GENERAL, title="Kept")
    await _add_messages(message_repository, kept.session_id, 2)

    await service.delete("alice", deleted.session_id)

    assert await service.get("alice", kept.session_id) == kept
    assert message_repository.count(kept.session_id) == 2


async def test_delete_of_missing_session_does_nothing(service: SessionService) -> None:
    await service.delete("alice", str(ULID()))


async def test_delete_of_other_users_session_leaves_it_and_its_messages(
    service: SessionService, message_repository: InMemoryMessageRepository
) -> None:
    session = await service.create("alice", module=ChatModule.GENERAL)
    await _add_messages(message_repository, session.session_id, 3)

    await service.delete("bob", session.session_id)

    assert await service.get("alice", session.session_id) == session
    assert message_repository.count(session.session_id) == 3


async def test_delete_retry_after_failed_message_delete_finishes(
    service: SessionService, message_repository: InMemoryMessageRepository
) -> None:
    session = await service.create("alice", module=ChatModule.GENERAL)
    await _add_messages(message_repository, session.session_id, 3)
    message_repository.fail_delete_all_once = {session.session_id}

    with pytest.raises(StorageUnavailableError):
        await service.delete("alice", session.session_id)
    await service.delete("alice", session.session_id)

    with pytest.raises(SessionNotFoundError):
        await service.get("alice", session.session_id)
    assert message_repository.count(session.session_id) == 0


async def test_delete_all_removes_every_session_of_the_user(
    service: SessionService, message_repository: InMemoryMessageRepository
) -> None:
    created = [
        await service.create("alice", module=ChatModule.GENERAL) for _ in range(MANY_SESSIONS)
    ]
    await _add_messages(message_repository, created[0].session_id, 2)

    await service.delete_all("alice")

    page = await service.list_page("alice", limit=50, cursor=None)
    assert page.items == ()
    assert message_repository.count(created[0].session_id) == 0


async def test_delete_all_leaves_other_users_sessions(service: SessionService) -> None:
    await service.create("alice", module=ChatModule.GENERAL)
    bobs = await service.create("bob", module=ChatModule.GENERAL)

    await service.delete_all("alice")

    assert await service.get("bob", bobs.session_id) == bobs


async def test_list_messages_returns_owned_sessions_messages(
    service: SessionService, message_repository: InMemoryMessageRepository
) -> None:
    session = await service.create("alice", module=ChatModule.GENERAL)
    await _add_messages(message_repository, session.session_id, 3)

    page = await service.list_messages("alice", session.session_id, limit=10, cursor=None)

    assert [message.content for message in page.items] == ["Message 2", "Message 1", "Message 0"]


async def test_list_messages_of_other_users_session_raises_not_found(
    service: SessionService, message_repository: InMemoryMessageRepository
) -> None:
    session = await service.create("alice", module=ChatModule.GENERAL)
    await _add_messages(message_repository, session.session_id, 3)

    with pytest.raises(SessionNotFoundError):
        await service.list_messages("bob", session.session_id, limit=10, cursor=None)
