from typing import Any

from domain.login import AuthProfileReference, AuthSession, SessionStatus
from topology.tables import RUNS_TABLE, SESSION_REQUESTS_TABLE, SESSIONS_TABLE

from ..values import (
    number_from_item,
    optional_number,
    optional_string,
    string_from_item,
)


def session_item(
    session: AuthSession,
    expires_at: float,
    updated_at: str,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "sessionId": {"S": session.session_id},
        "archiveId": {"S": session.archive_id},
        "targetUrl": {"S": session.target_url},
        "status": {"S": str(session.status)},
        "expiresAt": {"S": session.expires_at},
        "expiresAtEpoch": {"N": str(int(expires_at))},
        "managerId": {"S": session.manager_id},
        "version": {"N": str(session.version)},
        "createdAt": {"S": updated_at},
        "updatedAt": {"S": updated_at},
    }

    if session.auth_generation is not None:
        item["authGeneration"] = {"N": str(session.auth_generation)}

    if session.profile_key is not None:
        item["profileKey"] = {"S": session.profile_key}

    if session.vnc_origin is not None:
        item["vncOrigin"] = {"S": session.vnc_origin}

    return item


def session_from_item(item: dict[str, Any]) -> AuthSession:
    return AuthSession(
        session_id=string_from_item(item, "sessionId", "auth session"),
        archive_id=string_from_item(item, "archiveId", "auth session"),
        target_url=string_from_item(item, "targetUrl", "auth session"),
        status=SessionStatus(string_from_item(item, "status", "auth session")),
        expires_at=string_from_item(item, "expiresAt", "auth session"),
        manager_id=string_from_item(item, "managerId", "auth session"),
        version=int(number_from_item(item, "version", "auth session")),
        auth_generation=optional_number(item, "authGeneration"),
        profile_key=optional_string(item, "profileKey"),
        vnc_origin=optional_string(item, "vncOrigin"),
        failure_reason=optional_string(item, "failureReason"),
    )


def profile_reference_from_item(item: dict[str, Any]) -> AuthProfileReference | None:
    generation = optional_number(item, "authGeneration")
    key = optional_string(item, "authProfileKey")

    if generation is None or key is None:
        return None

    return AuthProfileReference(generation=generation, key=key)


def create_session_transaction(
    client: Any,
    session: AuthSession,
    key: str,
    fingerprint: str,
    expires_at: float,
    now_epoch: int,
    updated_at: str,
) -> None:
    client.transact_write_items(
        TransactItems=[
            {
                "Put": {
                    "TableName": SESSIONS_TABLE,
                    "Item": session_item(session, expires_at, updated_at),
                    "ConditionExpression": "attribute_not_exists(sessionId)",
                }
            },
            {
                "Put": {
                    "TableName": SESSION_REQUESTS_TABLE,
                    "Item": {
                        "idempotencyKey": {"S": key},
                        "sessionId": {"S": session.session_id},
                        "fingerprint": {"S": fingerprint},
                        "expiresAtEpoch": {"N": str(int(expires_at))},
                    },
                    "ConditionExpression": (
                        "attribute_not_exists(idempotencyKey) OR expiresAtEpoch <= :now"
                    ),
                    "ExpressionAttributeValues": {":now": {"N": str(now_epoch)}},
                }
            },
        ]
    )


def read_session(client: Any, session_id: str) -> dict[str, Any] | None:
    response = client.get_item(
        TableName=SESSIONS_TABLE,
        Key={"sessionId": {"S": session_id}},
        ConsistentRead=True,
    )

    return response.get("Item")


def read_session_request(client: Any, key: str) -> dict[str, Any] | None:
    response = client.get_item(
        TableName=SESSION_REQUESTS_TABLE,
        Key={"idempotencyKey": {"S": key}},
        ConsistentRead=True,
    )

    return response.get("Item")


def update_session(client: Any, session: AuthSession, updated_at: str) -> None:
    names = {"#status": "status", "#version": "version", "#updated": "updatedAt"}
    values: dict[str, Any] = {
        ":status": {"S": str(session.status)},
        ":version": {"N": str(session.version)},
        ":expected": {"N": str(session.version - 1)},
        ":updated": {"S": updated_at},
    }
    expression = "SET #status = :status, #version = :version, #updated = :updated"

    if session.auth_generation is not None:
        names["#generation"] = "authGeneration"
        values[":generation"] = {"N": str(session.auth_generation)}
        expression += ", #generation = :generation"

    if session.profile_key is not None:
        names["#profile"] = "profileKey"
        values[":profile"] = {"S": session.profile_key}
        expression += ", #profile = :profile"

    if session.vnc_origin is not None:
        names["#origin"] = "vncOrigin"
        values[":origin"] = {"S": session.vnc_origin}
        expression += ", #origin = :origin"

    if session.failure_reason is not None:
        names["#reason"] = "failureReason"
        values[":reason"] = {"S": session.failure_reason}
        expression += ", #reason = :reason"

    client.update_item(
        TableName=SESSIONS_TABLE,
        Key={"sessionId": {"S": session.session_id}},
        UpdateExpression=expression,
        ConditionExpression="#version = :expected",
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def update_generation(
    client: Any,
    archive_id: str,
    generation: int,
    current: int,
    updated_at: str,
) -> None:
    client.update_item(
        TableName=RUNS_TABLE,
        Key={"archiveId": {"S": archive_id}},
        UpdateExpression="SET authGeneration = :generation, authUpdatedAt = :updated",
        ConditionExpression=("attribute_not_exists(authGeneration) OR authGeneration = :current"),
        ExpressionAttributeValues={
            ":generation": {"N": str(generation)},
            ":current": {"N": str(current)},
            ":updated": {"S": updated_at},
        },
    )


def update_profile(
    client: Any,
    archive_id: str,
    generation: int,
    key: str,
    bucket: str,
    updated_at: str,
) -> None:
    client.update_item(
        TableName=RUNS_TABLE,
        Key={"archiveId": {"S": archive_id}},
        UpdateExpression=(
            "SET authProfileKey = :key, authProfileBucket = :bucket, authUpdatedAt = :updated"
        ),
        ConditionExpression="authGeneration = :generation",
        ExpressionAttributeValues={
            ":key": {"S": key},
            ":bucket": {"S": bucket},
            ":generation": {"N": str(generation)},
            ":updated": {"S": updated_at},
        },
    )


def scan_sessions(client: Any, cursor: dict[str, Any] | None) -> dict[str, Any]:
    request: dict[str, Any] = {"TableName": SESSIONS_TABLE}

    if cursor:
        request["ExclusiveStartKey"] = cursor

    return client.scan(**request)


def fail_session(
    client: Any,
    session: AuthSession,
    status: SessionStatus,
    reason: str,
    updated_at: str,
) -> None:
    client.update_item(
        TableName=SESSIONS_TABLE,
        Key={"sessionId": {"S": session.session_id}},
        UpdateExpression=(
            "SET #status = :status, #version = :version, #reason = :reason, #updated = :updated"
        ),
        ConditionExpression="#version = :expected",
        ExpressionAttributeNames={
            "#status": "status",
            "#version": "version",
            "#reason": "failureReason",
            "#updated": "updatedAt",
        },
        ExpressionAttributeValues={
            ":status": {"S": str(status)},
            ":version": {"N": str(session.version + 1)},
            ":expected": {"N": str(session.version)},
            ":reason": {"S": reason},
            ":updated": {"S": updated_at},
        },
    )
