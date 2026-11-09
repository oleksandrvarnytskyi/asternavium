# SPDX-License-Identifier: AGPL-3.0-or-later
"""Models for chat sessions and their messages."""

from typing import Annotated, Final

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from app.domain.chat import DEFAULT_SESSION_TITLE, ChatModule, MessageRole

SESSION_TITLE_MAX_LENGTH: Final = 100

SessionTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=SESSION_TITLE_MAX_LENGTH),
]


class SessionCreateRequest(BaseModel):
    """A new, empty session; temporary until ``POST /v1/chat`` creates sessions (decision D1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    module: ChatModule = Field(description="Module the session talks to.")
    title: SessionTitle = Field(
        default=DEFAULT_SESSION_TITLE,
        description=f"Display title, 1 to {SESSION_TITLE_MAX_LENGTH} characters after trimming.",
    )


class SessionRenameRequest(BaseModel):
    """A session's new title."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: SessionTitle = Field(
        description=f"Display title, 1 to {SESSION_TITLE_MAX_LENGTH} characters after trimming."
    )


class SessionResponse(BaseModel):
    """A chat session of the caller."""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    session_id: str = Field(description="Opaque session ID.")
    title: str = Field(description="Display title.")
    module: ChatModule = Field(description="Module the session talks to.")
    message_count: int = Field(description="Number of messages in the session.")
    created_at: AwareDatetime = Field(description="When the session was created, in UTC.")
    updated_at: AwareDatetime = Field(
        description="When the session was last renamed or written to, in UTC."
    )


class MessageResponse(BaseModel):
    """A message of a chat session."""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    message_id: str = Field(description="Opaque message ID.")
    role: MessageRole = Field(description="Author of the message.")
    content: str = Field(description="Message text.")
    created_at: AwareDatetime = Field(description="When the message was written, in UTC.")
