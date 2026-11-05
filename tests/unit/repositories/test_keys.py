# SPDX-License-Identifier: AGPL-3.0-or-later
import base64

import pytest
from hypothesis import given
from hypothesis import strategies as st
from ulid import ULID

from app.core.errors import InvalidCursorError
from app.repositories.keys import (
    MAX_CURSOR_LENGTH,
    MESSAGE_PREFIX,
    SESSION_PREFIX,
    decode_cursor,
    encode_cursor,
    id_from_key,
    message_key,
    session_key,
    user_key,
)

SESSION_ID = "01JBZ8M4N1T3QX6R9V2W5Y7K0C"


def _raw_cursor(text: str) -> str:
    """Encode arbitrary text the way a forged cursor would be."""
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()


def test_key_builders_use_documented_formats() -> None:
    assert user_key("alice") == "USER#alice"
    assert session_key(SESSION_ID) == f"SESSION#{SESSION_ID}"
    assert message_key(SESSION_ID) == f"MSG#{SESSION_ID}"


def test_id_from_key_strips_prefix() -> None:
    assert id_from_key(session_key(SESSION_ID), SESSION_PREFIX) == SESSION_ID


def test_id_from_key_rejects_key_with_other_prefix() -> None:
    with pytest.raises(ValueError, match="does not start with"):
        id_from_key(message_key(SESSION_ID), SESSION_PREFIX)


@given(st.builds(ULID))
def test_cursor_round_trips_sort_key(ulid: ULID) -> None:
    sort_key = session_key(str(ulid))

    cursor = encode_cursor(sort_key)

    assert decode_cursor(cursor, prefix=SESSION_PREFIX) == sort_key
    assert set(cursor) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


@pytest.mark.parametrize(
    "cursor",
    [
        pytest.param("", id="empty"),
        pytest.param("not base64!", id="not-base64"),
        pytest.param("A" * (MAX_CURSOR_LENGTH + 1), id="too-long"),
        pytest.param(_raw_cursor("SESSION#not-a-ulid"), id="not-a-ulid"),
        pytest.param(_raw_cursor(SESSION_ID), id="missing-prefix"),
        pytest.param(_raw_cursor(message_key(SESSION_ID)), id="other-list"),
        pytest.param(_raw_cursor(user_key("alice")), id="partition-key"),
        pytest.param(base64.urlsafe_b64encode(b"\xff\xfe").decode(), id="not-utf8"),
    ],
)
def test_decode_cursor_rejects_cursor_not_issued_for_list(cursor: str) -> None:
    with pytest.raises(InvalidCursorError) as caught:
        decode_cursor(cursor, prefix=SESSION_PREFIX)

    assert caught.value.code == "invalid_cursor"


def test_decode_cursor_rejects_session_cursor_for_messages() -> None:
    session_cursor = encode_cursor(session_key(SESSION_ID))

    with pytest.raises(InvalidCursorError):
        decode_cursor(session_cursor, prefix=MESSAGE_PREFIX)


def test_decode_cursor_error_message_omits_cursor() -> None:
    cursor = _raw_cursor("SESSION#forged")

    with pytest.raises(InvalidCursorError) as caught:
        decode_cursor(cursor, prefix=SESSION_PREFIX)

    assert cursor not in caught.value.message
