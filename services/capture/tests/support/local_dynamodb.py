import os
from collections.abc import Iterator

import boto3
import pytest
from mypy_boto3_dynamodb import DynamoDBClient


@pytest.fixture
def dynamodb_client() -> Iterator[DynamoDBClient]:
    client = boto3.client(
        "dynamodb",
        endpoint_url=os.environ.get("DYNAMODB_ENDPOINT_URL", "http://localhost:8000"),
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    client.create_table(
        TableName="capture_outbox",
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[{"AttributeName": "messageId", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "messageId", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
            {"AttributeName": "nextAttemptAt", "AttributeType": "N"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "status-nextAttemptAt-index",
                "KeySchema": [
                    {"AttributeName": "status", "KeyType": "HASH"},
                    {"AttributeName": "nextAttemptAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )

    try:
        yield client
    finally:
        client.delete_table(TableName="capture_outbox")
