# SPDX-License-Identifier: AGPL-3.0-or-later
"""Models for service health and build information."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class HealthResponse(BaseModel):
    """Liveness status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"] = "ok"


class AboutResponse(BaseModel):
    """Build and licence information; the source URL fulfils the AGPL-3.0 source offer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(description="Package version.")
    commit_sha: str | None = Field(description="Git commit of the running build, if known.")
    source_url: HttpUrl = Field(description="Where to obtain the corresponding source code.")
    license: str = Field(description="SPDX licence identifier.")
