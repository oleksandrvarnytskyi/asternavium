# SPDX-License-Identifier: AGPL-3.0-or-later
"""Definition of the app's single DynamoDB table.

This module is the one source of the table's keys, billing mode and TTL: the local table script
and the test fixtures create the table from it, and the Terraform ``data`` module (Phase 4)
must match it. Item key formats are built elsewhere, in the repositories' key module.
"""

import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient

logger = logging.getLogger(__name__)

PARTITION_KEY: Final = "PK"
SORT_KEY: Final = "SK"
# Epoch seconds; DynamoDB deletes the item some time after this instant.
TTL_ATTRIBUTE: Final = "expires_at"
_TTL_ACTIVE_STATUSES: Final = frozenset({"ENABLED", "ENABLING"})


def ensure_app_table(client: "DynamoDBClient", table_name: str) -> None:
    """Create the app table if it is missing, wait until it is active and enable TTL.

    Safe to run repeatedly: an existing table and an already enabled TTL are left as they are.

    :param client: DynamoDB client for the target account and region.
    :param table_name: Name of the table to create.
    :raises botocore.exceptions.ClientError: If AWS rejects a request.
    :raises botocore.exceptions.WaiterError: If the table does not become active in time.
    """
    try:
        client.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": PARTITION_KEY, "KeyType": "HASH"},
                {"AttributeName": SORT_KEY, "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": PARTITION_KEY, "AttributeType": "S"},
                {"AttributeName": SORT_KEY, "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        logger.info("Creating table %s", table_name)
    except client.exceptions.ResourceInUseException:
        logger.info("Table %s already exists", table_name)
    client.get_waiter("table_exists").wait(TableName=table_name)
    _ensure_ttl(client, table_name)


def _ensure_ttl(client: "DynamoDBClient", table_name: str) -> None:
    description = client.describe_time_to_live(TableName=table_name)["TimeToLiveDescription"]
    if description.get("TimeToLiveStatus") in _TTL_ACTIVE_STATUSES:
        return
    client.update_time_to_live(
        TableName=table_name,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": TTL_ATTRIBUTE},
    )
    logger.info("Enabled TTL on %s.%s", table_name, TTL_ATTRIBUTE)
