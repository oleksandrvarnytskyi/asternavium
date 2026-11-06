# SPDX-License-Identifier: AGPL-3.0-or-later
# All birth data here is synthetic; none of it belongs to a real person.
from datetime import UTC, date, datetime, time

import pytest
from service_fakes import (
    FakeClock,
    InMemoryMessageRepository,
    InMemoryProfileRepository,
    InMemorySessionRepository,
)
from ulid import ULID

from app.core.errors import StorageUnavailableError
from app.domain.birth_data import BirthData
from app.domain.chat import ChatModule, MessageRole
from app.domain.profile import AnswerDepth, Tradition
from app.repositories.geonames import GeoNamesPlaceRepository
from app.repositories.records import MessageRecord, SessionRecord
from app.services.accounts import AccountService
from app.services.profiles import ProfileService
from app.services.sessions import SessionService

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
# Kyiv in conftest.TEST_PLACE_RECORDS.
BIRTH = BirthData(local_date=date(1990, 5, 17), local_time=time(14, 30), place_id="4")


@pytest.fixture
def message_repository() -> InMemoryMessageRepository:
    return InMemoryMessageRepository()


@pytest.fixture
def profiles(place_repository: GeoNamesPlaceRepository) -> ProfileService:
    return ProfileService(InMemoryProfileRepository(), place_repository, clock=FakeClock(NOW))


@pytest.fixture
def sessions(message_repository: InMemoryMessageRepository) -> SessionService:
    return SessionService(InMemorySessionRepository(), message_repository, clock=FakeClock(NOW))


@pytest.fixture
def accounts(profiles: ProfileService, sessions: SessionService) -> AccountService:
    return AccountService(profiles, sessions)


async def _create_account(
    user_id: str,
    profiles: ProfileService,
    sessions: SessionService,
    messages: InMemoryMessageRepository,
) -> list[SessionRecord]:
    """Give the user a profile and two sessions with one message each."""
    await profiles.replace(
        user_id,
        birth=BIRTH,
        locale="en",
        tradition=Tradition.JYOTISHA,
        answer_depth=AnswerDepth.ESSENTIALS,
    )
    created = [await sessions.create(user_id, module=ChatModule.GENERAL) for _ in range(2)]
    for session in created:
        await messages.add(
            MessageRecord(
                session_id=session.session_id,
                message_id=str(ULID()),
                role=MessageRole.USER,
                content="Hello",
                created_at=NOW,
            )
        )
    return created


async def _assert_account_empty(
    user_id: str,
    removed: list[SessionRecord],
    profiles: ProfileService,
    sessions: SessionService,
    messages: InMemoryMessageRepository,
) -> None:
    assert await profiles.get(user_id) is None
    assert (await sessions.list_page(user_id, limit=50, cursor=None)).items == ()
    assert all(messages.count(session.session_id) == 0 for session in removed)


async def test_delete_removes_profile_sessions_and_messages(
    accounts: AccountService,
    profiles: ProfileService,
    sessions: SessionService,
    message_repository: InMemoryMessageRepository,
) -> None:
    created = await _create_account("alice", profiles, sessions, message_repository)

    await accounts.delete("alice")

    await _assert_account_empty("alice", created, profiles, sessions, message_repository)


async def test_delete_leaves_other_accounts(
    accounts: AccountService,
    profiles: ProfileService,
    sessions: SessionService,
    message_repository: InMemoryMessageRepository,
) -> None:
    await _create_account("alice", profiles, sessions, message_repository)
    bobs_sessions = await _create_account("bob", profiles, sessions, message_repository)

    await accounts.delete("alice")

    assert await profiles.get("bob") is not None
    assert len((await sessions.list_page("bob", limit=50, cursor=None)).items) == 2
    assert all(message_repository.count(session.session_id) == 1 for session in bobs_sessions)


async def test_delete_of_user_without_data_does_nothing(
    accounts: AccountService, profiles: ProfileService
) -> None:
    await accounts.delete("alice")

    assert await profiles.get("alice") is None


async def test_delete_retry_after_partial_failure_finishes(
    accounts: AccountService,
    profiles: ProfileService,
    sessions: SessionService,
    message_repository: InMemoryMessageRepository,
) -> None:
    created = await _create_account("alice", profiles, sessions, message_repository)
    # Sessions are deleted newest first, so the oldest one fails after the other is gone.
    oldest = min(created, key=lambda session: session.session_id)
    message_repository.fail_delete_all_once = {oldest.session_id}

    with pytest.raises(StorageUnavailableError):
        await accounts.delete("alice")
    assert len((await sessions.list_page("alice", limit=50, cursor=None)).items) == 1
    assert await profiles.get("alice") is not None

    await accounts.delete("alice")

    await _assert_account_empty("alice", created, profiles, sessions, message_repository)
