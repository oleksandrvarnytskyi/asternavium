# SPDX-License-Identifier: AGPL-3.0-or-later
# All birth data here is synthetic; none of it belongs to a real person.
import json
from datetime import date, time
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.birth_data import EARLIEST_BIRTH_DATE, AmbiguousTimeChoice, BirthData
from app.schemas.birth_data import PLACE_ID_MAX_LENGTH, BirthDataInput

VALID: dict[str, Any] = {"date": "1990-05-17", "time": "14:30", "place_id": "703448"}


def _parse(**changes: Any) -> BirthDataInput:
    """Validate the valid payload with some fields replaced; ``None`` removes a field."""
    payload = {**VALID, **changes}
    payload = {key: value for key, value in payload.items() if value is not None}
    return BirthDataInput.model_validate_json(json.dumps(payload))


def _error_messages(**changes: Any) -> list[str]:
    with pytest.raises(ValidationError) as caught:
        _parse(**changes)
    return [error["msg"] for error in caught.value.errors()]


def test_birth_data_input_converts_to_domain_value() -> None:
    birth = _parse(ambiguous_time="later").to_birth_data()

    assert birth == BirthData(
        local_date=date(1990, 5, 17),
        local_time=time(14, 30),
        place_id="703448",
        ambiguous_time=AmbiguousTimeChoice.LATER,
    )


def test_birth_data_input_ambiguous_time_defaults_to_none() -> None:
    assert _parse().ambiguous_time is None


@pytest.mark.parametrize("field", ["date", "time", "place_id"])
def test_birth_data_input_requires_field(field: str) -> None:
    assert _error_messages(**{field: None}) == ["Field required"]


def test_birth_data_input_accepts_earliest_birth_date() -> None:
    assert _parse(date=EARLIEST_BIRTH_DATE.isoformat()).date == EARLIEST_BIRTH_DATE


def test_birth_data_input_rejects_date_before_1900() -> None:
    messages = _error_messages(date="1899-12-31")

    assert messages == ["Input should be greater than or equal to 1900-01-01"]


def test_birth_data_input_accepts_leap_day() -> None:
    assert _parse(date="2000-02-29").date == date(2000, 2, 29)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("date", "2001-02-29", id="date-not-in-calendar"),
        pytest.param("date", 19900517, id="date-as-number"),
        pytest.param("time", 52200, id="time-as-seconds"),
        pytest.param("time", "25:00", id="time-out-of-range"),
        pytest.param("place_id", "", id="empty-place-id"),
        pytest.param("place_id", "x" * (PLACE_ID_MAX_LENGTH + 1), id="long-place-id"),
        pytest.param("ambiguous_time", "both", id="unknown-choice"),
    ],
)
def test_birth_data_input_rejects_malformed_value(field: str, value: object) -> None:
    assert len(_error_messages(**{field: value})) == 1


def test_birth_data_input_rejects_seconds() -> None:
    messages = _error_messages(time="14:30:15")

    assert messages == ["Value error, must be given to the minute, without seconds"]


def test_birth_data_input_rejects_utc_offset() -> None:
    messages = _error_messages(time="14:30+03:00")

    assert messages == [
        "Value error, must not include a UTC offset; the birth place sets the time zone"
    ]


@pytest.mark.parametrize("field", ["timezone", "latitude", "longitude"])
def test_birth_data_input_rejects_location_fields(field: str) -> None:
    assert _error_messages(**{field: "0"}) == ["Extra inputs are not permitted"]


def test_birth_data_input_error_messages_omit_submitted_values() -> None:
    messages = _error_messages(date="1899-12-31", time="14:30:15")

    assert not any("1899-12-31" in message or "14:30" in message for message in messages)
