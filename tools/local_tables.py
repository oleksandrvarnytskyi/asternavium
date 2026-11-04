# SPDX-License-Identifier: AGPL-3.0-or-later
"""Create or delete the local DynamoDB app table in the developer's AWS account.

Run ``make local-tables`` or ``make local-tables-delete``. The table name and region come from
the app settings (``.env``); credentials come from ``AWS_PROFILE``. Only tables whose names start
with ``asternavium-local-`` are touched, so other tables in the account stay safe.
"""

import argparse
import logging
from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.core.config import Settings
from app.core.logging import configure_logging
from app.repositories.app_table import ensure_app_table
from app.repositories.dynamodb import create_dynamodb_client

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient

logger = logging.getLogger(__name__)

LOCAL_TABLE_PREFIX: Final = "asternavium-local-"


class Command(StrEnum):
    """Supported script commands."""

    CREATE = "create"
    DELETE = "delete"


def require_local_table_name(table_name: str) -> None:
    """Refuse any table that is not a local development table.

    :raises ValueError: If ``table_name`` lacks the ``asternavium-local-`` prefix.
    """
    if not table_name.startswith(LOCAL_TABLE_PREFIX):
        msg = f"Refusing table {table_name!r}: local tables must start with {LOCAL_TABLE_PREFIX!r}"
        raise ValueError(msg)


def delete_app_table(client: "DynamoDBClient", table_name: str) -> None:
    """Delete the table if it exists and wait until it is gone; safe to run repeatedly.

    :raises botocore.exceptions.ClientError: If AWS rejects the request.
    :raises botocore.exceptions.WaiterError: If the table is not deleted in time.
    """
    try:
        client.delete_table(TableName=table_name)
        logger.info("Deleting table %s", table_name)
    except client.exceptions.ResourceNotFoundException:
        logger.info("Table %s does not exist", table_name)
        return
    client.get_waiter("table_not_exists").wait(TableName=table_name)


def run(command: Command, *, table_name: str, client: "DynamoDBClient") -> None:
    """Check the table name, then create or delete the table.

    :raises ValueError: If ``table_name`` is not a local table name.
    """
    require_local_table_name(table_name)
    match command:
        case Command.CREATE:
            ensure_app_table(client, table_name)
        case Command.DELETE:
            delete_app_table(client, table_name)
    logger.info("Done: %s %s", command.value, table_name)


def main(argv: Sequence[str] | None = None) -> None:
    """Parse arguments, load settings from the environment and ``.env``, and run the command."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("command", type=Command, choices=list(Command))
    args = parser.parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level)
    try:
        run(
            args.command,
            table_name=settings.app_table_name,
            client=create_dynamodb_client(settings),
        )
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
