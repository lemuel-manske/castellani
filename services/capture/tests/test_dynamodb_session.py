from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.domain import seed_run

from adapters.persistence.dynamodb.session import DynamoDBSessionStore
from application import DuplicateSessionRequest, SessionConflict
from domain import AuthSession, SessionStatus


@pytest.mark.integration
async def test_session_creation_is_idempotent_and_save_is_versioned(
    dynamodb: DynamoDBClient,
) -> None:
    store = new_store(dynamodb)

    await store.create(new_session(), "idempotency-1", "fingerprint-1")

    assert await store.find_by_request("idempotency-1", "fingerprint-1") == "session-1"

    active = replace(
        new_session(),
        status=SessionStatus.ACTIVE,
        version=2,
        vnc_origin="http://127.0.0.1:6080",
    )
    await store.save(active)

    with pytest.raises(SessionConflict):
        await store.save(replace(active, version=4))


@pytest.mark.integration
async def test_session_creation_rejects_a_reused_idempotency_key(
    dynamodb: DynamoDBClient,
) -> None:
    store = new_store(dynamodb)

    await store.create(new_session(), "idempotency-1", "fingerprint-1")

    with pytest.raises(DuplicateSessionRequest):
        await store.create(new_session(), "idempotency-1", "fingerprint-1")


@pytest.mark.integration
async def test_an_expired_idempotency_key_can_start_a_new_session(
    dynamodb: DynamoDBClient,
) -> None:
    store = new_store(dynamodb)

    await store.create(new_session("session-1"), "idempotency-1", "fingerprint-1")
    dynamodb.update_item(
        TableName="capture_session_requests",
        Key={"idempotencyKey": {"S": "idempotency-1"}},
        UpdateExpression="SET expiresAtEpoch = :expired",
        ExpressionAttributeValues={":expired": {"N": "0"}},
    )

    await store.create(new_session("session-2"), "idempotency-1", "fingerprint-1")

    assert await store.find_by_request("idempotency-1", "fingerprint-1") == "session-2"


@pytest.mark.integration
async def test_idempotency_key_reuse_with_another_request_is_a_conflict(
    dynamodb: DynamoDBClient,
) -> None:
    store = new_store(dynamodb)

    await store.create(new_session(), "idempotency-1", "fingerprint-1")

    with pytest.raises(SessionConflict):
        await store.find_by_request("idempotency-1", "fingerprint-2")


@pytest.mark.integration
async def test_generations_are_reserved_and_profile_references_are_pinned(
    dynamodb: DynamoDBClient,
) -> None:
    seed_run(dynamodb)
    store = new_store(dynamodb)

    generation = await store.reserve_generation("archive-1")
    await store.set_profile("archive-1", generation, "auth-profiles/archive-1/generation-1")

    run = dynamodb.get_item(
        TableName="capture_runs",
        Key={"archiveId": {"S": "archive-1"}},
        ConsistentRead=True,
    ).get("Item")

    assert run is not None
    assert (
        generation,
        int(run["authGeneration"].get("N", "0")),
        run["authProfileKey"].get("S"),
        run["authProfileBucket"].get("S"),
    ) == (
        1,
        "1",
        "auth-profiles/archive-1/generation-1",
        "castellani-auth-profiles",
    )


@pytest.mark.integration
async def test_stale_generation_cannot_replace_the_current_profile_reference(
    dynamodb: DynamoDBClient,
) -> None:
    seed_run(dynamodb)
    store = new_store(dynamodb)

    await store.reserve_generation("archive-1")
    await store.reserve_generation("archive-1")

    with pytest.raises(ClientError):
        await store.set_profile("archive-1", 1, "auth-profiles/archive-1/generation-1")


@pytest.mark.integration
async def test_start_reconciles_only_sessions_from_other_managers(
    dynamodb: DynamoDBClient,
) -> None:
    store = new_store(dynamodb)
    await store.create(new_session("session-1", "manager-1"), "key-1", "fingerprint-1")
    await store.create(new_session("session-2", "manager-2"), "key-2", "fingerprint-2")

    await store.reconcile_abandoned("manager-1")

    first = await store.get("session-1")
    second = await store.get("session-2")

    assert first is not None and second is not None
    assert (first.status, second.status, second.version) == (
        SessionStatus.ACTIVE,
        SessionStatus.FAILED,
        2,
    )


def new_store(dynamodb: DynamoDBClient) -> DynamoDBSessionStore:
    return DynamoDBSessionStore(
        client=dynamodb,
        session_ttl_seconds=1800,
        auth_profile_bucket="castellani-auth-profiles",
    )


def new_session(session_id: str = "session-1", manager_id: str = "manager-1") -> AuthSession:
    expires_at = datetime.now(UTC) + timedelta(seconds=1800)

    return AuthSession(
        session_id=session_id,
        archive_id="archive-1",
        target_url="https://example.org/",
        status=SessionStatus.ACTIVE,
        expires_at=expires_at.isoformat().replace("+00:00", "Z"),
        manager_id=manager_id,
        version=1,
    )
