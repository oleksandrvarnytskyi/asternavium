# SPDX-License-Identifier: AGPL-3.0-or-later
from mypy_boto3_dynamodb import DynamoDBClient

from app.repositories.app_table import (
    PARTITION_KEY,
    SORT_KEY,
    TTL_ATTRIBUTE,
    ensure_app_table,
)


def test_ensure_app_table_creates_active_table_with_string_keys(
    dynamodb_client: DynamoDBClient, app_table: str
) -> None:
    table = dynamodb_client.describe_table(TableName=app_table)["Table"]

    assert table["TableStatus"] == "ACTIVE"
    assert table["KeySchema"] == [
        {"AttributeName": PARTITION_KEY, "KeyType": "HASH"},
        {"AttributeName": SORT_KEY, "KeyType": "RANGE"},
    ]
    assert sorted(table["AttributeDefinitions"], key=lambda a: a["AttributeName"]) == [
        {"AttributeName": PARTITION_KEY, "AttributeType": "S"},
        {"AttributeName": SORT_KEY, "AttributeType": "S"},
    ]


def test_ensure_app_table_uses_on_demand_billing(
    dynamodb_client: DynamoDBClient, app_table: str
) -> None:
    table = dynamodb_client.describe_table(TableName=app_table)["Table"]

    assert table["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"


def test_ensure_app_table_enables_ttl_on_expires_at(
    dynamodb_client: DynamoDBClient, app_table: str
) -> None:
    ttl = dynamodb_client.describe_time_to_live(TableName=app_table)["TimeToLiveDescription"]

    assert ttl["TimeToLiveStatus"] == "ENABLED"
    assert ttl["AttributeName"] == TTL_ATTRIBUTE


def test_ensure_app_table_is_idempotent_for_existing_table(
    dynamodb_client: DynamoDBClient, app_table: str
) -> None:
    ensure_app_table(dynamodb_client, app_table)

    assert dynamodb_client.list_tables()["TableNames"] == [app_table]
    ttl = dynamodb_client.describe_time_to_live(TableName=app_table)["TimeToLiveDescription"]
    assert ttl["TimeToLiveStatus"] == "ENABLED"
