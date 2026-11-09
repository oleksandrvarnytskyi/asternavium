# SPDX-License-Identifier: AGPL-3.0-or-later
"""Records returned by the repositories; internal types, not API schemas.

Every timestamp is a timezone-aware UTC ``datetime``.
"""

from dataclasses import dataclass
from datetime import date, datetime, time

from app.domain.birth_data import AmbiguousTimeChoice
from app.domain.chat import ChatModule, MessageRole
from app.domain.profile import AnswerDepth, Tradition


@dataclass(frozen=True, slots=True)
class Page[T]:
    """One page of a list, newest first.

    :ivar items: Records on this page.
    :ivar next_cursor: Opaque cursor for the next page, or ``None`` on the last page.
    """

    items: tuple[T, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class BirthRecord:
    """Birth data as saved: the user's local input, the place copied at save time, and UTC.

    Copying the place means a later refresh of the place data never changes a saved profile.

    :ivar local_date: Birthdate at the birthplace.
    :ivar local_time: Wall-clock birth time at the birthplace, to the minute.
    :ivar ambiguous_time: Choice made for a time that occurred twice; ``None`` otherwise.
    :ivar place_id: Opaque ID of the birthplace.
    :ivar place_name: Display name of the birthplace at save time.
    :ivar place_region: First-level division of the birthplace (state, oblast) at save time,
        or ``None`` if the place data has none; with the country it tells apart places with
        the same name.
    :ivar place_country: Country of the birthplace in English at save time.
    :ivar latitude: Degrees north of the equator, -90 to 90 (WGS84).
    :ivar longitude: Degrees east of Greenwich, -180 to 180 (WGS84).
    :ivar timezone: IANA time zone name of the birthplace.
    :ivar places_dataset_version: Version of the place data the place was copied from.
    :ivar instant_utc: Birth instant computed from the local values and the zone.
    """

    local_date: date
    local_time: time
    ambiguous_time: AmbiguousTimeChoice | None
    place_id: str
    place_name: str
    place_region: str | None
    place_country: str
    latitude: float
    longitude: float
    timezone: str
    places_dataset_version: str
    instant_utc: datetime


@dataclass(frozen=True, slots=True)
class PersonRecord:
    """A person the user makes charts for: the user, a relative or a client.

    :ivar user_id: Owner; the person has no account of their own.
    :ivar person_id: ULID; sorts persons by creation time.
    :ivar label: The owner's name for the person, e.g. ``Me`` or ``Mum``.
    :ivar birth: Birth data; every person has it (decision D9).
    :ivar created_at: When the person was added.
    :ivar updated_at: When the person was last replaced.
    """

    user_id: str
    person_id: str
    label: str
    birth: BirthRecord
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    """A user's preferences; birth data lives on persons.

    :ivar user_id: Owner.
    :ivar locale: BCP 47 language tag for answers, e.g. ``uk``.
    :ivar traditions: Knowledge systems the user is interested in; non-empty, unordered.
    :ivar answer_depth: Default depth of answers.
    :ivar owner_person_id: The person who is the account owner, or ``None`` if not chosen.
    :ivar created_at: When the profile was first saved.
    :ivar updated_at: When the profile was last replaced.
    """

    user_id: str
    locale: str
    traditions: frozenset[Tradition]
    answer_depth: AnswerDepth
    owner_person_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """A chat session.

    :ivar user_id: Owner.
    :ivar session_id: ULID; sorts sessions by creation time.
    :ivar title: Display title.
    :ivar module: Module the session talks to.
    :ivar message_count: Number of messages; maintained from Phase 2.
    :ivar created_at: When the session was created.
    :ivar updated_at: When the session was last renamed or written to.
    """

    user_id: str
    session_id: str
    title: str
    module: ChatModule
    message_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MessageRecord:
    """A chat message.

    :ivar session_id: Session the message belongs to.
    :ivar message_id: ULID; sorts messages by creation time.
    :ivar role: Author.
    :ivar content: Message text.
    :ivar created_at: When the message was written.
    """

    session_id: str
    message_id: str
    role: MessageRole
    content: str
    created_at: datetime
