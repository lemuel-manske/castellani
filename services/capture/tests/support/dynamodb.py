import os
from typing import Any

from boto3.session import Session
from mypy_boto3_dynamodb.client import DynamoDBClient
from mypy_boto3_dynamodb.type_defs import CreateTableInputTypeDef

TABLES: tuple[CreateTableInputTypeDef, ...] = (
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


def new_dynamodb_client() -> DynamoDBClient:
    return Session().client(
        "dynamodb",
        endpoint_url=os.environ.get("DYNAMODB_ENDPOINT_URL"),
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


def setup_dynamodb(client: DynamoDBClient) -> None:
    for table in TABLES:
        client.create_table(**table)


def cleanup_dynamodb(client: DynamoDBClient) -> None:
    for table in reversed(TABLES):
        client.delete_table(TableName=table["TableName"])


def seed_run(client: DynamoDBClient, admission: str = "OPEN") -> None:
    client.put_item(
        TableName="capture_runs",
        Item={"archiveId": {"S": "archive-1"}, "admission": {"S": admission}},
    )


def seed_frontier(client: DynamoDBClient, depth: int = 0) -> None:
    client.put_item(
        TableName="capture_frontier",
        Item={
            "archiveId": {"S": "archive-1"},
            "urlKey": {"S": "url-1"},
            "url": {"S": "https://example.org/"},
            "depth": {"N": str(depth)},
            "state": {"S": "PENDING"},
        },
    )


def frontier_item(client: DynamoDBClient) -> dict[str, Any]:
    return client.get_item(
        TableName="capture_frontier",
        Key={"archiveId": {"S": "archive-1"}, "urlKey": {"S": "url-1"}},
        ConsistentRead=True,
    )["Item"]


def outbox_items(client: DynamoDBClient) -> list[dict[str, Any]]:
    return client.scan(TableName="capture_outbox", ConsistentRead=True)["Items"]


def set_run_admission(client: DynamoDBClient, admission: str) -> None:
    client.update_item(
        TableName="capture_runs",
        Key={"archiveId": {"S": "archive-1"}},
        UpdateExpression="SET admission = :admission",
        ExpressionAttributeValues={":admission": {"S": admission}},
    )
