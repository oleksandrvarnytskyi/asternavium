# SPDX-License-Identifier: AGPL-3.0-or-later
# All birth data here is synthetic; none of it belongs to a real person.
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

import pytest
from service_fakes import (
    FakeClock,
    InMemoryMessageRepository,
    InMemoryPersonRepository,
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
from app.services.persons import PersonService
from app.services.profiles import ProfileService
from app.services.sessions import SessionService

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
# Kyiv in conftest.TEST_PLACE_RECORDS.
BIRTH = BirthData(local_date=date(1990, 5, 17), local_time=time(14, 30), place_id="4")


@dataclass(frozen=True, slots=True)
class _Services:
    """The services an account spans, sharing one set of in-memory repositories."""

    profiles: ProfileService
    persons: PersonService
    sessions: SessionService
    messages: InMemoryMessageRepository
    accounts: AccountService


@pytest.fixture
def services(place_repository: GeoNamesPlaceRepository) -> _Services:
    clock = FakeClock(NOW)
    profile_repository = InMemoryProfileRepository()
    person_repository = InMemoryPersonRepository()
    message_repository = InMemoryMessageRepository()
    profiles = ProfileService(profile_repository, person_repository, clock=clock)
    persons = PersonService(person_repository, profile_repository, place_repository, clock=clock)
    sessions = SessionService(InMemorySessionRepository(), message_repository, clock=clock)
    return _Services(
        profiles=profiles,
        persons=persons,
        sessions=sessions,
        messages=message_repository,
        accounts=AccountService(profiles, persons, sessions),
    )


async def _create_account(services: _Services, user_id: str) -> list[SessionRecord]:
    """Give the user two persons, a profile linked to one, and two sessions with a message."""
    owner = await services.persons.create(user_id, label="Me", birth=BIRTH)
    await services.persons.create(user_id, label="Mum", birth=BIRTH)
    await services.profiles.replace(
        user_id,
        locale="en",
        traditions=frozenset({Tradition.JYOTISHA}),
        answer_depth=AnswerDepth.ESSENTIALS,
        owner_person_id=owner.person_id,
    )
    created = [await services.sessions.create(user_id, module=ChatModule.GENERAL) for _ in range(2)]
    for session in created:
        await services.messages.add(
            MessageRecord(
                session_id=session.session_id,
                message_id=str(ULID()),
                role=MessageRole.USER,
                content="Hello",
                created_at=NOW,
            )
        )
    return created


async def _session_count(services: _Services, user_id: str) -> int:
    return len((await services.sessions.list_page(user_id, limit=50, cursor=None)).items)


async def _person_count(services: _Services, user_id: str) -> int:
    return len((await services.persons.list_page(user_id, limit=50, cursor=None)).items)


async def _assert_account_empty(
    services: _Services, user_id: str, removed: list[SessionRecord]
) -> None:
    assert await services.profiles.get(user_id) is None
    assert await _person_count(services, user_id) == 0
    assert await _session_count(services, user_id) == 0
    assert all(services.messages.count(session.session_id) == 0 for session in removed)


async def test_delete_removes_profile_persons_sessions_and_messages(
    services: _Services,
) -> None:
    created = await _create_account(services, "alice")

    await services.accounts.delete("alice")

    await _assert_account_empty(services, "alice", created)


async def test_delete_leaves_other_accounts(services: _Services) -> None:
    await _create_account(services, "alice")
    bobs_sessions = await _create_account(services, "bob")

    await services.accounts.delete("alice")

    assert await services.profiles.get("bob") is not None
    assert await _person_count(services, "bob") == 2
    assert await _session_count(services, "bob") == 2
    assert all(services.messages.count(session.session_id) == 1 for session in bobs_sessions)


async def test_delete_of_user_without_data_does_nothing(services: _Services) -> None:
    await services.accounts.delete("alice")

    await _assert_account_empty(services, "alice", [])


async def test_delete_retry_after_partial_failure_finishes(services: _Services) -> None:
    created = await _create_account(services, "alice")
    # Sessions are deleted newest first, so the oldest one fails after the other is gone.
    oldest = min(created, key=lambda session: session.session_id)
    services.messages.fail_delete_all_once = {oldest.session_id}

    with pytest.raises(StorageUnavailableError):
        await services.accounts.delete("alice")
    assert await _session_count(services, "alice") == 1
    assert await _person_count(services, "alice") == 2
    assert await services.profiles.get("alice") is not None

    await services.accounts.delete("alice")

    await _assert_account_empty(services, "alice", created)
