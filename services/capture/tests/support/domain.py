from typing import Any

from mypy_boto3_dynamodb.client import DynamoDBClient

from domain.capture import PageTask, TaskClaim


def seed_run(
    client: DynamoDBClient,
    admission: str = "OPEN",
    max_pages: int = 100,
    admitted_pages: int = 1,
    auth_generation: int | None = None,
) -> None:
    item: dict[str, Any] = {
        "archiveId": {"S": "archive-1"},
        "admission": {"S": admission},
        "maxPages": {"N": str(max_pages)},
        "admittedPages": {"N": str(admitted_pages)},
        "outstandingPages": {"N": str(admitted_pages)},
    }

    if auth_generation is not None:
        item["authGeneration"] = {"N": str(auth_generation)}

    client.put_item(TableName="capture_runs", Item=item)


def seed_frontier(
    client: DynamoDBClient,
    depth: int = 0,
    url: str = "https://example.org/",
    url_key: str = "url-1",
) -> None:
    client.put_item(
        TableName="capture_frontier",
        Item={
            "archiveId": {"S": "archive-1"},
            "urlKey": {"S": url_key},
            "url": {"S": url},
            "depth": {"N": str(depth)},
            "state": {"S": "PENDING"},
        },
    )


def complete_frontier(client: DynamoDBClient) -> None:
    client.update_item(
        TableName="capture_frontier",
        Key={"archiveId": {"S": "archive-1"}, "urlKey": {"S": "url-1"}},
        UpdateExpression="SET #state = :state, #snapshot = :snapshot, #captured = :captured",
        ExpressionAttributeNames={
            "#state": "state",
            "#snapshot": "snapshotId",
            "#captured": "capturedAt",
        },
        ExpressionAttributeValues={
            ":state": {"S": "COMPLETED"},
            ":snapshot": {"S": "snapshot-1"},
            ":captured": {"S": "2026-11-24T10:00:00Z"},
        },
    )


def fail_frontier(client: DynamoDBClient) -> None:
    client.update_item(
        TableName="capture_frontier",
        Key={"archiveId": {"S": "archive-1"}, "urlKey": {"S": "url-1"}},
        UpdateExpression="SET #state = :state, #reason = :reason",
        ExpressionAttributeNames={
            "#state": "state",
            "#reason": "failureReason",
        },
        ExpressionAttributeValues={
            ":state": {"S": "FAILED"},
            ":reason": {"S": "navigation_failed"},
        },
    )


def seed_snapshot(client: DynamoDBClient, archive_id: str = "archive-1") -> None:
    client.put_item(
        TableName="capture_snapshots",
        Item={
            "snapshotId": {"S": "snapshot-1"},
            "archiveId": {"S": archive_id},
            "url": {"S": "https://example.org/"},
            "finalUrl": {"S": "https://example.org/final"},
            "capturedAt": {"S": "2026-11-24T10:00:00Z"},
            "contentType": {"S": "text/html"},
        },
    )


def frontier_item(
    client: DynamoDBClient,
    url_key: str = "url-1",
    archive_id: str = "archive-1",
) -> dict[str, Any]:
    return client.get_item(
        TableName="capture_frontier",
        Key={"archiveId": {"S": archive_id}, "urlKey": {"S": url_key}},
        ConsistentRead=True,
    ).get("Item", {})


def outbox_item(client: DynamoDBClient, message_id: str = "message-1") -> dict[str, Any]:
    return client.get_item(
        TableName="capture_outbox",
        Key={"messageId": {"S": message_id}},
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


def run_item(client: DynamoDBClient, archive_id: str = "archive-1") -> dict[str, Any]:
    return client.get_item(
        TableName="capture_runs",
        Key={"archiveId": {"S": archive_id}},
        ConsistentRead=True,
    ).get("Item", {})


def set_run_admission(client: DynamoDBClient, admission: str) -> None:
    client.update_item(
        TableName="capture_runs",
        Key={"archiveId": {"S": "archive-1"}},
        UpdateExpression="SET admission = :admission",
        ExpressionAttributeValues={":admission": {"S": admission}},
    )


def set_run_auth_generation(client: DynamoDBClient, generation: int) -> None:
    client.update_item(
        TableName="capture_runs",
        Key={"archiveId": {"S": "archive-1"}},
        UpdateExpression="SET #generation = :generation",
        ExpressionAttributeNames={"#generation": "authGeneration"},
        ExpressionAttributeValues={":generation": {"N": str(generation)}},
    )


def set_run_auth_profile(client: DynamoDBClient, generation: int, key: str) -> None:
    client.update_item(
        TableName="capture_runs",
        Key={"archiveId": {"S": "archive-1"}},
        UpdateExpression=("SET #generation = :generation, #profile = :profile, #bucket = :bucket"),
        ExpressionAttributeNames={
            "#generation": "authGeneration",
            "#profile": "authProfileKey",
            "#bucket": "authProfileBucket",
        },
        ExpressionAttributeValues={
            ":generation": {"N": str(generation)},
            ":profile": {"S": key},
            ":bucket": {"S": "castellani-auth-profiles"},
        },
    )


def set_run_publication(
    client: DynamoDBClient,
    decision: str = "PUBLISH",
    replay_status: str = "READY",
    package_key: str | None = None,
) -> None:
    names = {
        "#decision": "decision",
        "#replay": "replayStatus",
    }
    values: dict[str, Any] = {
        ":decision": {"S": decision},
        ":replay": {"S": replay_status},
    }
    expression = "SET #decision = :decision, #replay = :replay"

    if package_key is not None:
        names["#package"] = "packageKey"
        values[":package"] = {"S": package_key}
        expression += ", #package = :package"

    client.update_item(
        TableName="capture_runs",
        Key={"archiveId": {"S": "archive-1"}},
        UpdateExpression=expression,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def make_claim() -> TaskClaim:
    return TaskClaim(
        task=PageTask("archive/one", "url-key", "https://example.org/", 0),
        attempt_id="attempt-1",
        fence=1,
        lease_until=100,
    )
