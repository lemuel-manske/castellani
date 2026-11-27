import asyncio
import threading
from pathlib import Path
from typing import Any

import pytest
from crawler.results import CaptureLimits
from mypy_boto3_dynamodb.client import DynamoDBClient
from mypy_boto3_s3.client import S3Client
from support.domain import (
    frontier_item,
    outbox_items,
    run_item,
    seed_frontier,
    seed_run,
    set_run_auth_generation,
    set_run_auth_profile,
    specific_snapshot_item,
)
from support.recording import LocalSite

from adapters.artifacts.auth import AuthProfileCipher, EncryptedAuthProfileStore
from adapters.artifacts.local import LocalArtifactStore
from adapters.browser.executor import BrowserPageExecutor
from adapters.persistence.dynamodb.alloc import DynamoDBCaptureAllocator
from adapters.persistence.dynamodb.session import DynamoDBSessionStore
from adapters.persistence.dynamodb.task import DynamoDBTaskRepository
from application.capture import StoredAuthContexts
from capture.worker.runner import ConcreteCaptureWorker

LOCAL_LIMITS = CaptureLimits(allow_private_networks=True)

AUTH_PROFILE_KEY = b"k" * 32


@pytest.mark.integration
async def test_worker_discards_real_attempt_artifacts_after_capture_failure(
    dynamodb: DynamoDBClient,
    local_site: LocalSite,
    s3: S3Client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb, url=f"{local_site.base_url}/slow")

    monkeypatch.setattr("crawler.page.DOWNLOAD_EVENT_TIMEOUT_SECONDS", 0.05)

    worker = new_worker(
        dynamodb,
        LocalArtifactStore(tmp_path),
        s3,
        limits=CaptureLimits(
            navigation_timeout_milliseconds=100,
            allow_private_networks=True,
        ),
    )

    assert await worker("archive-1", "url-1")

    task = frontier_item(dynamodb)

    assert task["state"] == {"S": "FAILED"}
    assert task["failureReason"] == {"S": "navigation_failed"}
    assert "browser navigation did not produce" in task["failureMessage"]["S"]

    assert not (tmp_path / "attempt-1").exists()


@pytest.mark.integration
async def test_worker_completes_with_real_dynamodb_and_artifact_storage(
    dynamodb: DynamoDBClient,
    local_site: LocalSite,
    s3: S3Client,
    tmp_path: Path,
) -> None:
    url = f"{local_site.base_url}/page"

    seed_run(dynamodb)
    seed_frontier(dynamodb, url=url)

    worker = new_worker(dynamodb, LocalArtifactStore(tmp_path), s3)

    assert await worker("archive-1", "url-1")

    completed = frontier_item(dynamodb)

    assert completed["state"] == {"S": "COMPLETED"}
    assert completed["snapshotId"]["S"]

    snapshot = specific_snapshot_item(dynamodb, completed["snapshotId"]["S"])

    assert snapshot["url"] == {"S": url}
    assert snapshot["statusCode"] == {"N": "200"}
    assert snapshot["title"] == {"S": "Recorder acceptance page"}

    warc_files = tuple((tmp_path / "attempt-1").rglob("*.warc.gz"))

    assert warc_files
    assert all(path.stat().st_size > 0 for path in warc_files)

    events = outbox_items(dynamodb)

    assert {event["type"]["S"] for event in events} == {"PageCaptured", "CapturePage"}

    page_captured = next(event for event in events if event["type"] == {"S": "PageCaptured"})

    payload = page_captured["payload"]["M"]

    assert payload["archiveId"] == {"S": "archive-1"}
    assert payload["snapshotId"] == completed["snapshotId"]
    assert payload["url"] == {"S": url}
    assert payload["warcArtifacts"]["L"][0]["M"]["sha256"]["S"]

    run = run_item(dynamodb)

    assert run["admittedPages"] == {"N": "2"}
    assert run["outstandingPages"] == {"N": "1"}
    assert run["completedPages"] == {"N": "1"}


@pytest.mark.integration
async def test_worker_requeues_task_when_auth_generation_changes(
    dynamodb: DynamoDBClient,
    local_site: LocalSite,
    s3: S3Client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_run(dynamodb, auth_generation=1)
    seed_frontier(dynamodb, url=f"{local_site.base_url}/slow")

    profiles = EncryptedAuthProfileStore(s3, AuthProfileCipher(AUTH_PROFILE_KEY))
    state: dict[str, list[str]] = {"cookies": [], "origins": []}
    key = await profiles.save("archive-1", 1, state)
    set_run_auth_profile(dynamodb, 1, key)

    profile_loaded = threading.Event()
    original_get_object = s3.get_object

    def get_object(*args: Any, **kwargs: Any) -> Any:
        result = original_get_object(*args, **kwargs)
        profile_loaded.set()

        return result

    monkeypatch.setattr(s3, "get_object", get_object)

    async def renew_auth() -> None:
        await asyncio.to_thread(profile_loaded.wait)
        await asyncio.to_thread(set_run_auth_generation, dynamodb, 2)

    worker = new_worker(dynamodb, LocalArtifactStore(tmp_path), s3)
    renewal = asyncio.create_task(renew_auth())

    assert await worker("archive-1", "url-1")

    await renewal

    assert frontier_item(dynamodb)["state"] == {"S": "PENDING"}
    assert run_item(dynamodb)["authGeneration"] == {"N": "2"}
    assert run_item(dynamodb)["outstandingPages"] == {"N": "1"}

    events = outbox_items(dynamodb)

    assert [event["type"]["S"] for event in events] == ["CapturePage"]
    assert not (tmp_path / "attempt-1").exists()


@pytest.mark.integration
async def test_worker_requeues_task_when_real_allocator_has_no_available_slot(
    dynamodb: DynamoDBClient,
    local_site: LocalSite,
    s3: S3Client,
    tmp_path: Path,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb, url=f"{local_site.base_url}/page")

    allocator = DynamoDBCaptureAllocator(
        client=dynamodb,
        slot_count=1,
        lease_duration=30,
    )

    held = await allocator.reserve("other-attempt")
    assert held is not None

    worker = new_worker(dynamodb, LocalArtifactStore(tmp_path), s3)

    assert await worker("archive-1", "url-1")
    assert frontier_item(dynamodb)["state"] == {"S": "PENDING"}

    events = outbox_items(dynamodb)

    assert [event["type"]["S"] for event in events] == ["CapturePage"]
    assert events[0]["payload"]["M"]["urlKey"] == {"S": "url-1"}
    assert dynamodb.scan(TableName="capture_snapshots")["Items"] == []
    assert not (tmp_path / "attempt-1").exists()


def new_worker(
    dynamodb: DynamoDBClient,
    artifacts: LocalArtifactStore,
    s3: S3Client,
    limits: CaptureLimits = LOCAL_LIMITS,
) -> ConcreteCaptureWorker:
    return ConcreteCaptureWorker(
        task_repository=DynamoDBTaskRepository(
            client=dynamodb,
            lease_duration=30,
        ),
        capture_allocator=DynamoDBCaptureAllocator(
            client=dynamodb,
            slot_count=1,
            lease_duration=30,
        ),
        executor=BrowserPageExecutor(limits),
        artifacts=artifacts,
        auth_contexts=StoredAuthContexts(
            sessions=DynamoDBSessionStore(client=dynamodb),
            profiles=EncryptedAuthProfileStore(s3, AuthProfileCipher(AUTH_PROFILE_KEY)),
        ),
    )
