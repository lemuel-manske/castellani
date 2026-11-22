from typing import Any

from mypy_boto3_dynamodb.client import DynamoDBClient

from domain import PageTask, TaskClaim


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


def snapshot_item(client: DynamoDBClient) -> dict[str, Any]:
    return client.get_item(
        TableName="capture_snapshots",
        Key={"snapshotId": {"S": "snapshot-1"}},
        ConsistentRead=True,
    ).get("Item", {})


def specific_snapshot_item(client: DynamoDBClient, snapshot_id: str) -> dict[str, Any]:
    return client.get_item(
        TableName="capture_snapshots",
        Key={"snapshotId": {"S": snapshot_id}},
        ConsistentRead=True,
    ).get("Item", {})


def run_item(client: DynamoDBClient) -> dict[str, Any]:
    return client.get_item(
        TableName="capture_runs",
        Key={"archiveId": {"S": "archive-1"}},
        ConsistentRead=True,
    ).get("Item", {})


def set_run_admission(client: DynamoDBClient, admission: str) -> None:
    client.update_item(
        TableName="capture_runs",
        Key={"archiveId": {"S": "archive-1"}},
        UpdateExpression="SET admission = :admission",
        ExpressionAttributeValues={":admission": {"S": admission}},
    )


def make_claim() -> TaskClaim:
    return TaskClaim(
        task=PageTask("archive/one", "url-key", "https://example.org/", 0),
        attempt_id="attempt-1",
        fence=1,
        lease_until=100,
    )
