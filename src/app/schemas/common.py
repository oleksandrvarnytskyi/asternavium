# SPDX-License-Identifier: AGPL-3.0-or-later
"""Models and constraints shared by several resources."""

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

# IDs of sessions and persons are ULIDs as this API issues them: 26 upper-case Crockford base32
# characters, the first at most 7. Anything else cannot name an item and is rejected early.
ULID_PATTERN: Final = r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"


class PageResponse[ItemT: BaseModel](BaseModel):
    """One page of a list, newest first."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[ItemT] = Field(description="Items on this page; empty if there are none.")
    next_cursor: str | None = Field(
        description="Pass as ``cursor`` to get the next page; ``null`` on the last page."
    )
