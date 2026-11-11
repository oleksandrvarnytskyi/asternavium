# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application settings loaded from environment variables."""

from enum import StrEnum
from typing import Final

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_AWS_REGION: Final = "eu-central-1"
_AWS_REGION_PATTERN: Final = r"^[a-z]{2}(-[a-z]+)+-\d+$"
# DynamoDB table naming rules: 3 to 255 characters of letters, digits, "_", "-" and ".".
_DYNAMODB_TABLE_NAME_PATTERN: Final = r"^[A-Za-z0-9_.-]{3,255}$"


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
    aws_region: str = Field(
        default=DEFAULT_AWS_REGION,
        pattern=_AWS_REGION_PATTERN,
        description="AWS region of the app's DynamoDB table.",
    )
    app_table_name: str = Field(
        pattern=_DYNAMODB_TABLE_NAME_PATTERN,
        description="Name of the DynamoDB table holding profiles, persons, sessions and messages.",
    )
