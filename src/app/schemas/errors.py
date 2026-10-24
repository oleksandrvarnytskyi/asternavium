# SPDX-License-Identifier: AGPL-3.0-or-later
"""Error response model shared by all endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class FieldError(BaseModel):
    """One failed validation rule, without the rejected input value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    loc: list[str] = Field(description="Path to the invalid field, e.g. ``['body', 'message']``.")
    msg: str = Field(description="Human-readable reason.")


class ErrorResponse(BaseModel):
    """Body of every non-2xx response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable explanation without personal data.")
    request_id: str | None = Field(description="ID to quote when reporting the problem.")
    details: list[FieldError] | None = Field(
        default=None, description="Per-field problems for validation errors."
    )
