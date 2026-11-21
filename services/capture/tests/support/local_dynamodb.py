import os
from collections.abc import Iterator
from typing import Any

import boto3
import pytest


TABLES = (
    {
        "TableName": "capture_browser_slots",
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "slotId", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "slotId", "AttributeType": "S"}],
    },
    {
        "TableName": "capture_runs",
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "archiveId", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "archiveId", "AttributeType": "S"}],
    },
    {
        "TableName": "capture_frontier",
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [
            {"AttributeName": "archiveId", "KeyType": "HASH"},
            {"AttributeName": "urlKey", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "archiveId", "AttributeType": "S"},
            {"AttributeName": "urlKey", "AttributeType": "S"},
        ],
    },
    {
        "TableName": "capture_outbox",
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "messageId", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "messageId", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
            {"AttributeName": "nextAttemptAt", "AttributeType": "N"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "status-nextAttemptAt-index",
                "KeySchema": [
                    {"AttributeName": "status", "KeyType": "HASH"},
                    {"AttributeName": "nextAttemptAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
)


@pytest.fixture
def dynamodb_client() -> Iterator[Any]:
    client = boto3.client(
        "dynamodb",
        endpoint_url=os.environ.get("DYNAMODB_ENDPOINT_URL", "http://localhost:8000"),
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )

    for table in TABLES:
        client.create_table(**table)

    try:
        yield client
    finally:
        for table in reversed(TABLES):
            client.delete_table(TableName=table["TableName"])
