# SPDX-License-Identifier: AGPL-3.0-or-later
"""Chat sessions and messages vocabulary."""

from enum import StrEnum
from typing import Final

DEFAULT_SESSION_TITLE: Final = "New chat"


class ChatModule(StrEnum):
    """Module a chat session talks to."""

    JYOTISHA = "jyotisha"
    BUKVITSA = "bukvitsa"
    GENERAL = "general"


class MessageRole(StrEnum):
    """Author of a chat message."""

    USER = "user"
    ASSISTANT = "assistant"
