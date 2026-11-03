# SPDX-License-Identifier: AGPL-3.0-or-later
"""DynamoDB client construction."""

from typing import TYPE_CHECKING, Final

import boto3
from botocore.config import Config

from app.core.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient

CONNECT_TIMEOUT_SECONDS: Final = 2.0
READ_TIMEOUT_SECONDS: Final = 5.0
# Total attempts including the first; "standard" mode backs off exponentially with jitter.
MAX_ATTEMPTS: Final = 3
RETRY_MODE: Final = "standard"


def create_dynamodb_client(settings: Settings) -> "DynamoDBClient":
    """Create a DynamoDB client for the configured region.

    Credentials come from the standard AWS chain (for example ``AWS_PROFILE``), never from
    settings. A dedicated session avoids shared state in ``boto3``'s default session.

    :param settings: Application settings; ``aws_region`` selects the endpoint.
    :returns: Client with explicit timeouts and a bounded retry policy.
    """
    config = Config(
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        read_timeout=READ_TIMEOUT_SECONDS,
        retries={"total_max_attempts": MAX_ATTEMPTS, "mode": RETRY_MODE},
    )
    session = boto3.session.Session(region_name=settings.aws_region)
    return session.client("dynamodb", config=config)
