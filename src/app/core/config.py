# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application settings loaded from environment variables."""

from enum import StrEnum

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment."""

    DEV = "dev"
    PROD = "prod"


class LogLevel(StrEnum):
    """Supported root log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """Runtime configuration; every field maps to an ``ASTERNAVIUM_``-prefixed env variable."""

    model_config = SettingsConfigDict(
        env_prefix="ASTERNAVIUM_",
        env_file=".env",
        extra="forbid",
        frozen=True,
    )

    environment: Environment = Field(default=Environment.DEV, description="Deployment environment.")
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Root log level.")
    source_url: HttpUrl = Field(
        description="Public URL of this service's source code, required by the AGPL-3.0."
    )
    commit_sha: str | None = Field(
        default=None,
        max_length=40,
        description="Git commit the running build was made from; set by the build pipeline.",
    )
