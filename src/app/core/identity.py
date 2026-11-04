# SPDX-License-Identifier: AGPL-3.0-or-later
"""Identity of the caller an API request acts for."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated caller.

    :ivar user_id: Stable user ID; already validated, safe to use in storage keys.
    """

    user_id: str
