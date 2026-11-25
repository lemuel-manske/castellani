import os

from boto3.session import Session
from mypy_boto3_dynamodb.client import DynamoDBClient
from mypy_boto3_dynamodb.type_defs import CreateTableInputTypeDef

TABLES: tuple[CreateTableInputTypeDef, ...] = (
    {
        "TableName": "capture_snapshots",
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "snapshotId", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "snapshotId", "AttributeType": "S"},
            {"AttributeName": "archiveId", "AttributeType": "S"},
            {"AttributeName": "capturedAt", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "archiveId-capturedAt-index",
                "KeySchema": [
                    {"AttributeName": "archiveId", "KeyType": "HASH"},
                    {"AttributeName": "capturedAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
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
        "TableName": "capture_sessions",
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "sessionId", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "sessionId", "AttributeType": "S"},
        ],
    },
    {
        "TableName": "capture_session_requests",
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [{"AttributeName": "idempotencyKey", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "idempotencyKey", "AttributeType": "S"},
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
    endpoint_url = os.environ.get("CAPTURE_DYNAMODB_ENDPOINT_URL")

    return Session().client(
        "dynamodb",
        endpoint_url=endpoint_url,
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
