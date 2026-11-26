from typing import Any

from adapters.serialization import artifact_document
from contracts.messages import (
    ARCHIVE_COMPENSATED_EVENT,
    ARCHIVE_PREPARED_EVENT,
    ARCHIVE_PUBLISHED_EVENT,
    ArchiveCompensatedPayload,
    ArchivePreparedPayload,
    ArchivePublishedPayload,
)
from domain.capture import (
    DECISION_COMPENSATE,
    DECISION_PUBLISH,
    PACKAGE_PENDING,
    PACKAGE_PREPARED,
    PACKAGE_PREPARING,
    REPLAY_READY,
    CompensationDecision,
    PendingPackage,
    PreparedPackage,
    PublicationDecision,
)
from topology.tables import OUTBOX_TABLE, RUNS_TABLE

from ..values import optional_number, optional_string, serialize_map, string_from_item


def pending_package_scan() -> dict[str, Any]:
    return {
        "TableName": RUNS_TABLE,
        "FilterExpression": (
            "#manifest_status = :published "
            "AND (#package_status = :pending OR attribute_not_exists(#package_status) "
            "OR (#package_status = :preparing AND #lease < :now)) "
            "AND attribute_not_exists(#package_digest) "
            "AND attribute_not_exists(#decision) "
            "AND (attribute_not_exists(#lease) OR #lease < :now)"
        ),
        "ExpressionAttributeNames": {
            "#manifest_status": "manifestStatus",
            "#package_status": "packageStatus",
            "#package_digest": "packageDigest",
            "#decision": "decision",
            "#lease": "packageLeaseUntil",
        },
        "ExpressionAttributeValues": {
            ":published": {"S": "PUBLISHED"},
            ":pending": {"S": PACKAGE_PENDING},
            ":preparing": {"S": PACKAGE_PREPARING},
            ":now": {"N": "0"},
        },
        "ConsistentRead": True,
    }


def pending_package_from_item(item: dict[str, Any]) -> PendingPackage:
    return PendingPackage(
        archive_id=string_from_item(item, "archiveId", "capture run"),
        manifest_key=string_from_item(item, "manifestKey", "capture run"),
        manifest_digest=string_from_item(item, "manifestDigest", "capture run"),
        closed_at=string_from_item(item, "closedAt", "capture run"),
        lease_owner=optional_string(item, "packageLeaseOwner") or "",
    )


def claim_package_update(
    archive_id: str,
    now: float,
    lease_until: float,
    owner: str,
) -> dict[str, Any]:
    return {
        "TableName": RUNS_TABLE,
        "Key": {"archiveId": {"S": archive_id}},
        "UpdateExpression": "SET #status = :preparing, #lease = :lease, #owner = :owner",
        "ConditionExpression": (
            "#manifest_status = :published "
            "AND (#status = :pending OR attribute_not_exists(#status) "
            "OR (#status = :preparing AND #lease < :now)) "
            "AND attribute_not_exists(#digest) "
            "AND attribute_not_exists(#decision) "
            "AND (attribute_not_exists(#lease) OR #lease < :now)"
        ),
        "ExpressionAttributeNames": {
            "#manifest_status": "manifestStatus",
            "#status": "packageStatus",
            "#digest": "packageDigest",
            "#decision": "decision",
            "#lease": "packageLeaseUntil",
            "#owner": "packageLeaseOwner",
        },
        "ExpressionAttributeValues": {
            ":published": {"S": "PUBLISHED"},
            ":pending": {"S": PACKAGE_PENDING},
            ":preparing": {"S": PACKAGE_PREPARING},
            ":lease": {"N": str(lease_until)},
            ":now": {"N": str(now)},
            ":owner": {"S": owner},
        },
    }


def release_package_update(archive_id: str, owner: str) -> dict[str, Any]:
    return {
        "TableName": RUNS_TABLE,
        "Key": {"archiveId": {"S": archive_id}},
        "UpdateExpression": "SET #status = :pending REMOVE #lease, #owner",
        "ConditionExpression": "#status = :preparing AND #owner = :owner",
        "ExpressionAttributeNames": {
            "#status": "packageStatus",
            "#lease": "packageLeaseUntil",
            "#owner": "packageLeaseOwner",
        },
        "ExpressionAttributeValues": {
            ":pending": {"S": PACKAGE_PENDING},
            ":preparing": {"S": PACKAGE_PREPARING},
            ":owner": {"S": owner},
        },
    }


def prepare_package_transaction(
    prepared: PreparedPackage,
    message_id: str,
    occurred_at: str,
    now: float,
) -> list[dict[str, Any]]:
    artifact = prepared.artifact
    payload: ArchivePreparedPayload = {
        "archiveId": prepared.archive_id,
        "package": artifact_document(artifact),
        "packageDigest": artifact.sha256,
        "manifestDigest": prepared.manifest_digest,
    }

    return [
        {
            "Update": {
                "TableName": RUNS_TABLE,
                "Key": {"archiveId": {"S": prepared.archive_id}},
                "UpdateExpression": (
                    "SET #status = :prepared, #bucket = :bucket, #key = :key, "
                    "#digest = :digest, #size = :size, "
                    "#manifest_digest = :manifest_digest REMOVE #lease, #owner"
                ),
                "ConditionExpression": (
                    "#manifest_status = :published "
                    "AND (#status = :preparing OR #status = :pending) "
                    "AND attribute_not_exists(#digest) "
                    "AND attribute_not_exists(#decision) "
                    "AND #owner = :owner"
                ),
                "ExpressionAttributeNames": {
                    "#manifest_status": "manifestStatus",
                    "#status": "packageStatus",
                    "#bucket": "packageBucket",
                    "#key": "packageKey",
                    "#digest": "packageDigest",
                    "#size": "packageSizeBytes",
                    "#manifest_digest": "packageManifestDigest",
                    "#decision": "decision",
                    "#lease": "packageLeaseUntil",
                    "#owner": "packageLeaseOwner",
                },
                "ExpressionAttributeValues": {
                    ":published": {"S": "PUBLISHED"},
                    ":preparing": {"S": PACKAGE_PREPARING},
                    ":pending": {"S": PACKAGE_PENDING},
                    ":prepared": {"S": PACKAGE_PREPARED},
                    ":owner": {"S": prepared.lease_owner},
                    ":bucket": {"S": artifact.bucket},
                    ":key": {"S": artifact.key},
                    ":digest": {"S": artifact.sha256},
                    ":size": {"N": str(artifact.size_bytes)},
                    ":manifest_digest": {"S": prepared.manifest_digest},
                },
            }
        },
        {
            "Put": {
                "TableName": OUTBOX_TABLE,
                "Item": {
                    "messageId": {"S": message_id},
                    "correlationId": {"S": prepared.archive_id},
                    "type": {"S": ARCHIVE_PREPARED_EVENT},
                    "version": {"N": "1"},
                    "occurredAt": {"S": occurred_at},
                    "payload": {"M": serialize_map(payload)},
                    "status": {"S": "PENDING"},
                    "attempts": {"N": "0"},
                    "nextAttemptAt": {"N": str(now)},
                },
                "ConditionExpression": "attribute_not_exists(#message_id)",
                "ExpressionAttributeNames": {"#message_id": "messageId"},
            }
        },
    ]


def publication_transaction(
    decision: PublicationDecision,
    message_id: str,
    now: float,
) -> list[dict[str, Any]]:
    payload: ArchivePublishedPayload = {
        "archiveId": decision.archive_id,
        "decisionVersion": decision.decision_version,
        "packageDigest": decision.package_digest,
    }

    return [
        {
            "Update": {
                "TableName": RUNS_TABLE,
                "Key": {"archiveId": {"S": decision.archive_id}},
                "UpdateExpression": (
                    "SET #decision = :publish, #decision_version = :version, "
                    "#replay_status = :ready"
                ),
                "ConditionExpression": (
                    "#package_digest = :package_digest "
                    "AND (attribute_not_exists(#decision) OR #decision = :publish) "
                    "AND (attribute_not_exists(#decision_version) OR #decision_version <= :version)"
                ),
                "ExpressionAttributeNames": {
                    "#decision": "decision",
                    "#decision_version": "decisionVersion",
                    "#replay_status": "replayStatus",
                    "#package_digest": "packageDigest",
                },
                "ExpressionAttributeValues": {
                    ":publish": {"S": DECISION_PUBLISH},
                    ":version": {"N": str(decision.decision_version)},
                    ":ready": {"S": REPLAY_READY},
                    ":package_digest": {"S": decision.package_digest},
                },
            }
        },
        {
            "Put": {
                "TableName": OUTBOX_TABLE,
                "Item": {
                    "messageId": {"S": message_id},
                    "correlationId": {"S": decision.archive_id},
                    "type": {"S": ARCHIVE_PUBLISHED_EVENT},
                    "version": {"N": "1"},
                    "occurredAt": {"S": decision.occurred_at},
                    "payload": {"M": serialize_map(payload)},
                    "status": {"S": "PENDING"},
                    "attempts": {"N": "0"},
                    "nextAttemptAt": {"N": str(now)},
                },
                "ConditionExpression": "attribute_not_exists(#message_id)",
                "ExpressionAttributeNames": {"#message_id": "messageId"},
            }
        },
    ]


def compensation_update(decision: CompensationDecision) -> dict[str, Any]:
    return {
        "TableName": RUNS_TABLE,
        "Key": {"archiveId": {"S": decision.archive_id}},
        "UpdateExpression": "SET #decision = :compensate, #decision_version = :version",
        "ConditionExpression": (
            "(attribute_not_exists(#decision) OR #decision = :compensate) "
            "AND (attribute_not_exists(#decision_version) OR #decision_version <= :version)"
        ),
        "ExpressionAttributeNames": {
            "#decision": "decision",
            "#decision_version": "decisionVersion",
        },
        "ExpressionAttributeValues": {
            ":compensate": {"S": DECISION_COMPENSATE},
            ":version": {"N": str(decision.decision_version)},
        },
    }


def compensation_transaction(
    decision: CompensationDecision,
    message_id: str,
    now: float,
) -> dict[str, Any]:
    payload: ArchiveCompensatedPayload = {
        "archiveId": decision.archive_id,
        "decisionVersion": decision.decision_version,
    }

    return {
        "Put": {
            "TableName": OUTBOX_TABLE,
            "Item": {
                "messageId": {"S": message_id},
                "correlationId": {"S": decision.archive_id},
                "type": {"S": ARCHIVE_COMPENSATED_EVENT},
                "version": {"N": "1"},
                "occurredAt": {"S": decision.occurred_at},
                "payload": {"M": serialize_map(payload)},
                "status": {"S": "PENDING"},
                "attempts": {"N": "0"},
                "nextAttemptAt": {"N": str(now)},
            },
            "ConditionExpression": "attribute_not_exists(#message_id)",
            "ExpressionAttributeNames": {"#message_id": "messageId"},
        }
    }


def is_prepared_message(item: dict[str, Any], archive_id: str, digest: str) -> bool:
    payload = item.get("payload", {}).get("M", {})

    return (
        item.get("type", {}).get("S") == ARCHIVE_PREPARED_EVENT
        and item.get("correlationId", {}).get("S") == archive_id
        and payload.get("archiveId", {}).get("S") == archive_id
        and payload.get("packageDigest", {}).get("S") == digest
    )


def is_published_message(item: dict[str, Any], decision: PublicationDecision) -> bool:
    payload = item.get("payload", {}).get("M", {})

    return (
        item.get("type", {}).get("S") == ARCHIVE_PUBLISHED_EVENT
        and item.get("correlationId", {}).get("S") == decision.archive_id
        and payload.get("archiveId", {}).get("S") == decision.archive_id
        and payload.get("decisionVersion", {}).get("N") == str(decision.decision_version)
        and payload.get("packageDigest", {}).get("S") == decision.package_digest
    )


def is_compensated_message(item: dict[str, Any], decision: CompensationDecision) -> bool:
    payload = item.get("payload", {}).get("M", {})

    return (
        item.get("type", {}).get("S") == ARCHIVE_COMPENSATED_EVENT
        and item.get("correlationId", {}).get("S") == decision.archive_id
        and payload.get("archiveId", {}).get("S") == decision.archive_id
        and payload.get("decisionVersion", {}).get("N") == str(decision.decision_version)
    )


def is_prepared_package(item: dict[str, Any], prepared: PreparedPackage) -> bool:
    return (
        optional_string(item, "packageDigest") == prepared.artifact.sha256
        and optional_string(item, "packageManifestDigest") == prepared.manifest_digest
    )


def is_published_decision(item: dict[str, Any], decision: PublicationDecision) -> bool:
    return (
        optional_string(item, "decision") == DECISION_PUBLISH
        and optional_number(item, "decisionVersion") == decision.decision_version
        and optional_string(item, "packageDigest") == decision.package_digest
    )


def is_compensating_decision(item: dict[str, Any], decision: CompensationDecision) -> bool:
    return (
        optional_string(item, "decision") == DECISION_COMPENSATE
        and optional_number(item, "decisionVersion") == decision.decision_version
    )


def scan_pending_packages(
    client: Any,
    now: float,
    cursor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = pending_package_scan()
    request["ExpressionAttributeValues"][":now"] = {"N": str(now)}

    if cursor:
        request["ExclusiveStartKey"] = cursor

    return client.scan(**request)


def claim_package(
    client: Any,
    archive_id: str,
    now: float,
    lease_until: float,
    owner: str,
) -> None:
    client.update_item(**claim_package_update(archive_id, now, lease_until, owner))


def release_package(client: Any, archive_id: str, owner: str) -> None:
    client.update_item(**release_package_update(archive_id, owner))


def prepare_package(
    client: Any,
    prepared: PreparedPackage,
    message_id: str,
    occurred_at: str,
    now: float,
) -> None:
    client.transact_write_items(
        TransactItems=prepare_package_transaction(prepared, message_id, occurred_at, now)
    )


def publish_package(
    client: Any,
    decision: PublicationDecision,
    message_id: str,
    now: float,
) -> None:
    client.transact_write_items(TransactItems=publication_transaction(decision, message_id, now))


def begin_compensation(client: Any, decision: CompensationDecision) -> None:
    client.update_item(**compensation_update(decision))


def complete_compensation(
    client: Any,
    decision: CompensationDecision,
    message_id: str,
    now: float,
) -> None:
    client.transact_write_items(TransactItems=[compensation_transaction(decision, message_id, now)])
