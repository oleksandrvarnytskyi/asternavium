# SPDX-License-Identifier: AGPL-3.0-or-later
"""Key formats of the app table and the pagination cursor codec.

The only module that builds keys, so every key format exists in one place:

========  ======================  ======================
Item      PK                      SK
========  ======================  ======================
Profile   ``USER#<user_id>``      ``PROFILE``
Person    ``USER#<user_id>``      ``PERSON#<ulid>``
Session   ``USER#<user_id>``      ``SESSION#<ulid>``
Message   ``SESSION#<ulid>``      ``MSG#<ulid>``
========  ======================  ======================
"""

import base64
import binascii
from typing import Final

from ulid import ULID

from app.core.errors import InvalidCursorError

USER_PREFIX: Final = "USER#"
PERSON_PREFIX: Final = "PERSON#"
SESSION_PREFIX: Final = "SESSION#"
MESSAGE_PREFIX: Final = "MSG#"
PROFILE_SORT_KEY: Final = "PROFILE"
# A cursor encodes one sort key: a prefix and a 26-character ULID, well under this limit.
MAX_CURSOR_LENGTH: Final = 128
_BASE64_BLOCK: Final = 4
_URL_SAFE_ALTCHARS: Final = b"-_"
_INVALID_CURSOR_MESSAGE: Final = "The cursor is invalid; request the first page again."


def user_key(user_id: str) -> str:
    """Return the partition key of everything a user owns."""
    return f"{USER_PREFIX}{user_id}"


def person_key(person_id: str) -> str:
    """Return the sort key of a person under its owner."""
    return f"{PERSON_PREFIX}{person_id}"


def session_key(session_id: str) -> str:
    """Return the session's key: its sort key under the user and its messages' partition key."""
    return f"{SESSION_PREFIX}{session_id}"


def message_key(message_id: str) -> str:
    """Return the sort key of a message under its session."""
    return f"{MESSAGE_PREFIX}{message_id}"


def id_from_key(key: str, prefix: str) -> str:
    """Return the ID part of a key built by this module, e.g. the ULID of ``SESSION#<ulid>``.

    :raises ValueError: If ``key`` does not start with ``prefix``; stored data is corrupt.
    """
    if not key.startswith(prefix):
        msg = f"key does not start with {prefix!r}"
        raise ValueError(msg)
    return key.removeprefix(prefix)


def encode_cursor(sort_key: str) -> str:
    """Encode the sort key of a page's last item as an opaque, URL-safe cursor."""
    return base64.urlsafe_b64encode(sort_key.encode("utf-8")).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str, *, prefix: str) -> str:
    """Decode a cursor back into a sort key and check it belongs to the requested list.

    Only the sort key is encoded; the partition key always comes from the caller, so a cursor
    can never move a query into another user's or session's items.

    :param prefix: Sort key prefix of the list, e.g. :data:`SESSION_PREFIX`.
    :raises InvalidCursorError: If the cursor is malformed or was issued for another list.
    """
    if len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidCursorError(_INVALID_CURSOR_MESSAGE)
    padded = cursor + "=" * (-len(cursor) % _BASE64_BLOCK)
    try:
        sort_key = base64.b64decode(padded, altchars=_URL_SAFE_ALTCHARS, validate=True).decode()
        ULID.from_str(sort_key.removeprefix(prefix))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise InvalidCursorError(_INVALID_CURSOR_MESSAGE) from None
    if not sort_key.startswith(prefix):
        raise InvalidCursorError(_INVALID_CURSOR_MESSAGE)
    return sort_key
