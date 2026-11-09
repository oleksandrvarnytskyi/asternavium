# SPDX-License-Identifier: AGPL-3.0-or-later
"""Path and query parameters shared by several routers."""

from typing import Annotated, Final

from fastapi import Path, Query

from app.schemas.common import ULID_PATTERN

DEFAULT_PAGE_SIZE: Final = 20
MAX_PAGE_SIZE: Final = 50

LimitQuery = Annotated[
    int, Query(ge=1, le=MAX_PAGE_SIZE, description="Maximum number of items on the page.")
]
# The repositories reject a cursor they did not issue, including an overlong one.
CursorQuery = Annotated[
    str | None,
    Query(description="``next_cursor`` of the previous page; omit for the first page."),
]
SessionIdPath = Annotated[
    str, Path(pattern=ULID_PATTERN, description="Session ID from GET /v1/sessions.")
]
PersonIdPath = Annotated[
    str, Path(pattern=ULID_PATTERN, description="Person ID from GET /v1/persons.")
]
