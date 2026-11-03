# SPDX-License-Identifier: AGPL-3.0-or-later
from app.core.config import Settings
from app.repositories.dynamodb import (
    CONNECT_TIMEOUT_SECONDS,
    MAX_ATTEMPTS,
    READ_TIMEOUT_SECONDS,
    RETRY_MODE,
    create_dynamodb_client,
)


def test_create_dynamodb_client_uses_configured_region(settings: Settings) -> None:
    regional = settings.model_copy(update={"aws_region": "us-east-1"})

    client = create_dynamodb_client(regional)

    assert client.meta.region_name == "us-east-1"


def test_create_dynamodb_client_sets_timeouts_and_bounded_retries(settings: Settings) -> None:
    client = create_dynamodb_client(settings)

    # botocore sets Config options dynamically, so the stubs do not declare them as attributes.
    options = vars(client.meta.config)
    assert options["connect_timeout"] == CONNECT_TIMEOUT_SECONDS
    assert options["read_timeout"] == READ_TIMEOUT_SECONDS
    assert options["retries"] == {"total_max_attempts": MAX_ATTEMPTS, "mode": RETRY_MODE}
