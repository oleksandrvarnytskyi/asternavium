"""Models for service health and build information."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class HealthResponse(BaseModel):
    """Liveness status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"] = "ok"


class DataAttributionResponse(BaseModel):
    """Credit for one third-party dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(description="Name of the dataset or its publisher.")
    url: HttpUrl = Field(description="Where the data comes from.")
    license: str = Field(description="SPDX identifier of the data licence.")
    license_url: HttpUrl = Field(description="Full text of the data licence.")


class AboutResponse(BaseModel):
    """Build information and the credits for third-party data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(description="Package version.")
    commit_sha: str | None = Field(description="Git commit of the running build, if known.")
    attributions: list[DataAttributionResponse] = Field(
        description="Third-party datasets the service uses, with their licences."
    )
