# SPDX-License-Identifier: AGPL-3.0-or-later
"""User preferences stored with the profile."""

from enum import StrEnum
from typing import Final

DEFAULT_LOCALE: Final = "en"
# BCP 47 subset: language, optional script and optional region, e.g. "en", "uk", "sr-Latn-RS".
LOCALE_PATTERN: Final = r"^[a-z]{2,3}(-[A-Z][a-z]{3})?(-([A-Z]{2}|\d{3}))?$"


class Tradition(StrEnum):
    """Knowledge system the user prefers answers from."""

    JYOTISHA = "jyotisha"
    BUKVITSA = "bukvitsa"


class AnswerDepth(StrEnum):
    """How deep and technical answers should be; describes the answers, never the user.

    It changes how results are explained, never what is calculated. The profile holds the
    user's default; from Phase 2 a chat request may override it for one answer.
    """

    ESSENTIALS = "essentials"
    DETAILED = "detailed"
    TECHNICAL = "technical"


DEFAULT_TRADITION: Final = Tradition.JYOTISHA
DEFAULT_ANSWER_DEPTH: Final = AnswerDepth.ESSENTIALS
