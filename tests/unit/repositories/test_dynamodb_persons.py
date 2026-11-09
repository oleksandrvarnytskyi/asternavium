# SPDX-License-Identifier: AGPL-3.0-or-later
# All birth data here is synthetic; none of it belongs to a real person.
import dataclasses
from datetime import UTC, date, datetime, time, timedelta

import pytest
from ulid import ULID

from app.core.errors import InvalidCursorError, PersonNotFoundError
from app.domain.birth_data import AmbiguousTimeChoice
from app.repositories.dynamodb_persons import DynamoDBPersonRepository
from app.repositories.records import BirthRecord, PersonRecord

pytestmark = pytest.mark.anyio

START = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
UPDATED = datetime(2026, 11, 5, 9, 30, tzinfo=UTC)
BIRTH = BirthRecord(
    local_date=date(1990, 5, 17),
    local_time=time(14, 30),
    ambiguous_time=None,
    place_id="703448",
    place_name="Kyiv",
    place_region="Kyiv City",
    place_country="Ukraine",
    latitude=50.45466,
    longitude=30.5238,
    timezone="Europe/Kyiv",
    places_dataset_version="2026-11-04",
    instant_utc=datetime(1990, 5, 17, 10, 30, tzinfo=UTC),
)


def _person(user_id: str = "alice", *, minute: int = 0, **changes: object) -> PersonRecord:
    """Build a person added ``minute`` minutes after START; later minutes sort newer."""
    created = START + timedelta(minutes=minute)
    person = PersonRecord(
        user_id=user_id,
        person_id=str(ULID.from_datetime(created)),
        label=f"Person {minute}",
        birth=BIRTH,
        created_at=created,
        updated_at=created,
    )
    return dataclasses.replace(person, **changes)  # type: ignore[arg-type]  # test-only overrides


async def test_create_then_get_round_trips_every_field(
    persons: DynamoDBPersonRepository,
) -> None:
    person = _person()

    await persons.create(person)

    assert await persons.get("alice", person.person_id) == person


async def test_create_round_trips_ambiguous_time_choice(
    persons: DynamoDBPersonRepository,
) -> None:
    birth = dataclasses.replace(
        BIRTH,
        local_date=date(2021, 10, 31),
        local_time=time(3, 30),
        ambiguous_time=AmbiguousTimeChoice.LATER,
        instant_utc=datetime(2021, 10, 31, 1, 30, tzinfo=UTC),
    )
    person = _person(birth=birth)

    await persons.create(person)

    assert await persons.get("alice", person.person_id) == person


async def test_create_round_trips_place_without_region(
    persons: DynamoDBPersonRepository,
) -> None:
    person = _person(birth=dataclasses.replace(BIRTH, place_region=None))

    await persons.create(person)

    assert await persons.get("alice", person.person_id) == person


async def test_create_rejects_existing_person_id(persons: DynamoDBPersonRepository) -> None:
    person = _person()
    await persons.create(person)

    with pytest.raises(ValueError, match="already exists"):
        await persons.create(person)


async def test_get_returns_none_for_other_users_person(
    persons: DynamoDBPersonRepository,
) -> None:
    person = _person("alice")
    await persons.create(person)

    assert await persons.get("bob", person.person_id) is None


async def test_list_page_returns_own_persons_newest_first(
    persons: DynamoDBPersonRepository,
) -> None:
    for minute in range(3):
        await persons.create(_person(minute=minute))
    await persons.create(_person("bob", minute=10))

    first = await persons.list_page("alice", limit=2, cursor=None)
    second = await persons.list_page("alice", limit=2, cursor=first.next_cursor)

    assert [person.label for person in first.items] == ["Person 2", "Person 1"]
    assert [person.label for person in second.items] == ["Person 0"]
    assert second.next_cursor is None


async def test_list_page_rejects_malformed_cursor(persons: DynamoDBPersonRepository) -> None:
    with pytest.raises(InvalidCursorError):
        await persons.list_page("alice", limit=10, cursor="not-a-cursor")


async def test_replace_overwrites_existing_person(persons: DynamoDBPersonRepository) -> None:
    person = _person()
    await persons.create(person)
    replacement = dataclasses.replace(person, label="Mum", updated_at=UPDATED)

    await persons.replace(replacement)

    assert await persons.get("alice", person.person_id) == replacement


async def test_replace_missing_person_raises_and_creates_nothing(
    persons: DynamoDBPersonRepository,
) -> None:
    person = _person()

    with pytest.raises(PersonNotFoundError):
        await persons.replace(person)

    assert await persons.get("alice", person.person_id) is None


async def test_replace_other_users_person_raises_not_found(
    persons: DynamoDBPersonRepository,
) -> None:
    person = _person("alice")
    await persons.create(person)

    with pytest.raises(PersonNotFoundError):
        await persons.replace(dataclasses.replace(person, user_id="bob", label="Hijacked"))

    assert await persons.get("alice", person.person_id) == person


async def test_delete_removes_only_that_person(persons: DynamoDBPersonRepository) -> None:
    deleted, kept = _person(minute=0), _person(minute=1)
    await persons.create(deleted)
    await persons.create(kept)

    await persons.delete("alice", deleted.person_id)

    assert await persons.get("alice", deleted.person_id) is None
    assert await persons.get("alice", kept.person_id) == kept


async def test_delete_is_idempotent(persons: DynamoDBPersonRepository) -> None:
    person = _person()
    await persons.create(person)

    await persons.delete("alice", person.person_id)
    await persons.delete("alice", person.person_id)

    assert await persons.get("alice", person.person_id) is None


async def test_delete_of_other_users_person_leaves_it(
    persons: DynamoDBPersonRepository,
) -> None:
    person = _person("alice")
    await persons.create(person)

    await persons.delete("bob", person.person_id)

    assert await persons.get("alice", person.person_id) == person
