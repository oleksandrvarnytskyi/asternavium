# SPDX-License-Identifier: AGPL-3.0-or-later
from unittest.mock import create_autospec

import pytest
from mypy_boto3_dynamodb import DynamoDBClient

from tools.local_tables import Command, require_local_table_name, run

LOCAL_TABLE = "asternavium-local-app"


@pytest.mark.parametrize("name", [LOCAL_TABLE, "asternavium-local-checkpoints"])
def test_require_local_table_name_accepts_local_prefix(name: str) -> None:
    require_local_table_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "asternavium-dev-app",
        "asternavium-prod-app",
        "asternavium-local",
        "other-asternavium-local-app",
        "",
    ],
)
def test_require_local_table_name_rejects_other_names(name: str) -> None:
    with pytest.raises(ValueError, match="asternavium-local-"):
        require_local_table_name(name)


@pytest.mark.parametrize("command", list(Command))
def test_run_rejects_non_local_table_before_calling_aws(command: Command) -> None:
    client = create_autospec(DynamoDBClient, instance=True)

    with pytest.raises(ValueError, match="asternavium-local-"):
        run(command, table_name="asternavium-prod-app", client=client)

    assert client.method_calls == []


def test_run_create_creates_local_table(dynamodb_client: DynamoDBClient) -> None:
    run(Command.CREATE, table_name=LOCAL_TABLE, client=dynamodb_client)

    table = dynamodb_client.describe_table(TableName=LOCAL_TABLE)["Table"]
    assert table["TableStatus"] == "ACTIVE"


def test_run_create_twice_keeps_one_table(dynamodb_client: DynamoDBClient) -> None:
    run(Command.CREATE, table_name=LOCAL_TABLE, client=dynamodb_client)
    run(Command.CREATE, table_name=LOCAL_TABLE, client=dynamodb_client)

    assert dynamodb_client.list_tables()["TableNames"] == [LOCAL_TABLE]


def test_run_delete_removes_local_table(dynamodb_client: DynamoDBClient) -> None:
    run(Command.CREATE, table_name=LOCAL_TABLE, client=dynamodb_client)

    run(Command.DELETE, table_name=LOCAL_TABLE, client=dynamodb_client)

    assert dynamodb_client.list_tables()["TableNames"] == []


def test_run_delete_of_missing_table_succeeds(dynamodb_client: DynamoDBClient) -> None:
    run(Command.DELETE, table_name=LOCAL_TABLE, client=dynamodb_client)

    assert dynamodb_client.list_tables()["TableNames"] == []
