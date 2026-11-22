from typing import Any

from mypy_boto3_dynamodb.client import DynamoDBClient


def seed_run(
    client: DynamoDBClient,
    admission: str = "OPEN",
    max_pages: int = 100,
    admitted_pages: int = 1,
) -> None:
    client.put_item(
        TableName="capture_runs",
        Item={
            "archiveId": {"S": "archive-1"},
            "admission": {"S": admission},
            "maxPages": {"N": str(max_pages)},
            "admittedPages": {"N": str(admitted_pages)},
            "outstandingPages": {"N": str(admitted_pages)},
        },
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
    ).get("Item", {})


def outbox_item(client: DynamoDBClient) -> dict[str, Any]:
    return client.get_item(
        TableName="capture_outbox",
        Key={"messageId": {"S": "message-1"}},
        ConsistentRead=True,
    ).get("Item", {})


def outbox_items(client: DynamoDBClient) -> list[dict[str, Any]]:
    return client.scan(TableName="capture_outbox", ConsistentRead=True)["Items"]


def set_run_admission(client: DynamoDBClient, admission: str) -> None:
    client.update_item(
        TableName="capture_runs",
        Key={"archiveId": {"S": "archive-1"}},
        UpdateExpression="SET admission = :admission",
        ExpressionAttributeValues={":admission": {"S": admission}},
    )
