# SPDX-License-Identifier: AGPL-3.0-or-later
"""Source of the current instant, injected so services stay deterministic under test."""

from collections.abc import Callable
from datetime import UTC, datetime

type Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Return the current instant as an aware UTC ``datetime``."""
    return datetime.now(UTC)
