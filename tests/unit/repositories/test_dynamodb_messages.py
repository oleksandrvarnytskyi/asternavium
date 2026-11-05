# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from ulid import ULID

from app.core.errors import InvalidCursorError, StorageUnavailableError
from app.domain.chat import ChatModule, MessageRole
from app.repositories import dynamodb_messages
from app.repositories.dynamodb_messages import MAX_BATCH_WRITE_ITEMS, DynamoDBMessageRepository
from app.repositories.dynamodb_sessions import DynamoDBSessionRepository
from app.repositories.records import MessageRecord, SessionRecord

pytestmark = pytest.mark.anyio

START = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
# More than two delete batches, so delete_all must loop.
MANY_MESSAGES = 2 * MAX_BATCH_WRITE_ITEMS + 10


def _message(session_id: str, *, second: int) -> MessageRecord:
    """Build a message written ``second`` seconds after START; later seconds sort newer."""
    created = START + timedelta(seconds=second)
    return MessageRecord(
        session_id=session_id,
        message_id=str(ULID.from_datetime(created)),
        role=MessageRole.USER if second % 2 == 0 else MessageRole.ASSISTANT,
        content=f"Message {second}",
        created_at=created,
    )


async def _add_messages(
    messages: DynamoDBMessageRepository, session_id: str, count: int
) -> list[MessageRecord]:
    added = [_message(session_id, second=second) for second in range(count)]
    for message in added:
        await messages.add(message)
    return added


async def _count(messages: DynamoDBMessageRepository, session_id: str) -> int:
    total = 0
    cursor: str | None = None
    while True:
        page = await messages.list_page(session_id, limit=50, cursor=cursor)
        total += len(page.items)
        if page.next_cursor is None:
            return total
        cursor = page.next_cursor


async def test_add_then_list_returns_message(messages: DynamoDBMessageRepository) -> None:
    session_id = str(ULID())
    message = _message(session_id, second=0)

    await messages.add(message)

    page = await messages.list_page(session_id, limit=10, cursor=None)
    assert page.items == (message,)


async def test_add_rejects_existing_message_id(messages: DynamoDBMessageRepository) -> None:
    message = _message(str(ULID()), second=0)
    await messages.add(message)

    with pytest.raises(ValueError, match="already exists"):
        await messages.add(message)


async def test_list_page_returns_newest_first_across_pages(
    messages: DynamoDBMessageRepository,
) -> None:
    session_id = str(ULID())
    await _add_messages(messages, session_id, 3)

    first = await messages.list_page(session_id, limit=2, cursor=None)
    second = await messages.list_page(session_id, limit=2, cursor=first.next_cursor)

    assert [message.content for message in first.items] == ["Message 2", "Message 1"]
    assert [message.content for message in second.items] == ["Message 0"]
    assert second.next_cursor is None


async def test_list_page_shows_only_that_sessions_messages(
    messages: DynamoDBMessageRepository,
) -> None:
    session_id, other_session_id = str(ULID()), str(ULID())
    await _add_messages(messages, session_id, 2)
    await _add_messages(messages, other_session_id, 3)

    page = await messages.list_page(session_id, limit=10, cursor=None)

    assert {message.session_id for message in page.items} == {session_id}


async def test_list_page_rejects_session_list_cursor(
    messages: DynamoDBMessageRepository, sessions: DynamoDBSessionRepository
) -> None:
    for minute in range(2):
        created = START + timedelta(minutes=minute)
        await sessions.create(
            SessionRecord(
                user_id="alice",
                session_id=str(ULID.from_datetime(created)),
                title="Chat",
                module=ChatModule.GENERAL,
                message_count=0,
                created_at=created,
                updated_at=created,
            )
        )
    session_cursor = (await sessions.list_page("alice", limit=1, cursor=None)).next_cursor

    with pytest.raises(InvalidCursorError):
        await messages.list_page(str(ULID()), limit=10, cursor=session_cursor)


async def test_delete_all_removes_every_message_in_batches(
    messages: DynamoDBMessageRepository,
) -> None:
    session_id = str(ULID())
    await _add_messages(messages, session_id, MANY_MESSAGES)

    await messages.delete_all(session_id)

    assert await _count(messages, session_id) == 0


async def test_delete_all_leaves_other_sessions(messages: DynamoDBMessageRepository) -> None:
    session_id, other_session_id = str(ULID()), str(ULID())
    await _add_messages(messages, session_id, 3)
    await _add_messages(messages, other_session_id, 4)

    await messages.delete_all(session_id)

    assert await _count(messages, other_session_id) == 4


async def test_delete_all_is_idempotent(messages: DynamoDBMessageRepository) -> None:
    session_id = str(ULID())
    await _add_messages(messages, session_id, 3)

    await messages.delete_all(session_id)
    await messages.delete_all(session_id)

    assert await _count(messages, session_id) == 0


async def test_session_delete_with_messages_removes_both(
    messages: DynamoDBMessageRepository, sessions: DynamoDBSessionRepository
) -> None:
    session = SessionRecord(
        user_id="alice",
        session_id=str(ULID()),
        title="Chat",
        module=ChatModule.JYOTISHA,
        message_count=0,
        created_at=START,
        updated_at=START,
    )
    await sessions.create(session)
    await _add_messages(messages, session.session_id, 5)

    await messages.delete_all(session.session_id)
    await sessions.delete("alice", session.session_id)

    assert await sessions.get("alice", session.session_id) is None
    assert await _count(messages, session.session_id) == 0


class _UnprocessedThenDone:
    """Wraps ``batch_write_item`` to leave every item unprocessed for the first few calls."""

    def __init__(self, real: Any, *, failures: int, table_name: str) -> None:
        self.real = real
        self.failures = failures
        self.table_name = table_name
        self.calls = 0

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if self.calls <= self.failures:
            return {"UnprocessedItems": kwargs["RequestItems"]}
        result: dict[str, Any] = self.real(**kwargs)
        return result


@pytest.fixture
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dynamodb_messages, "UNPROCESSED_RETRY_BASE_SECONDS", 0)


@pytest.mark.usefixtures("no_retry_wait")
async def test_delete_all_retries_unprocessed_items(
    messages: DynamoDBMessageRepository, app_table: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = str(ULID())
    await _add_messages(messages, session_id, 3)
    client = messages._client
    flaky = _UnprocessedThenDone(client.batch_write_item, failures=2, table_name=app_table)
    monkeypatch.setattr(client, "batch_write_item", flaky)

    await messages.delete_all(session_id)

    assert flaky.calls == 3
    assert await _count(messages, session_id) == 0


@pytest.mark.usefixtures("no_retry_wait")
async def test_delete_all_gives_up_when_items_stay_unprocessed(
    messages: DynamoDBMessageRepository, app_table: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = str(ULID())
    await _add_messages(messages, session_id, 3)
    client = messages._client
    stuck = _UnprocessedThenDone(client.batch_write_item, failures=1_000, table_name=app_table)
    monkeypatch.setattr(client, "batch_write_item", stuck)

    with pytest.raises(StorageUnavailableError):
        await messages.delete_all(session_id)

    assert stuck.calls == dynamodb_messages.MAX_UNPROCESSED_RETRIES + 1
    assert await _count(messages, session_id) == 3
