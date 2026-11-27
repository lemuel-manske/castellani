import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import pytest
from support.clock import SimpleClock
from support.fn import claim_outbox_message

from contracts.messages import PAGE_CAPTURED_EVENT
from domain.capture import (
    ArtifactReference,
    AuthGenerationChanged,
    CaptureOutcome,
    PageCapture,
    PageTask,
    StartCrawl,
    TaskClaim,
    TaskClaimLostError,
    identify_url,
)
from ports.capture import CrawlStarter, OutboxRepository, TaskRepository
from ports.login import SessionStore

pytestmark = pytest.mark.integration

WARC_ARTIFACT = ArtifactReference(
    bucket="warcs",
    key="warcs/seed.warc.gz",
    sha256="0" * 64,
    size_bytes=10,
)


async def test_claim_returns_the_seeded_page_task(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim == TaskClaim(
        task=PageTask(
            archive_id="archive-1",
            url_key=identity.url_key,
            url=identity.navigation_url,
            depth=0,
        ),
        attempt_id="attempt-1",
        fence=1,
        lease_until=1_800_000_060.0,
    )


async def test_claim_returns_none_for_an_unknown_page(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )

    assert await task_repository.claim("archive-1", "missing") is None


async def test_renew_extends_the_lease_without_changing_ownership(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    clock: SimpleClock,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    clock.advance(10.0)

    renewed = await task_repository.renew(claim)

    assert renewed == replace(claim, lease_until=1_800_000_070.0)


async def test_renew_rejects_a_released_claim(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    await task_repository.release(claim)

    with pytest.raises(TaskClaimLostError):
        await task_repository.renew(claim)


async def test_release_requeues_the_task_for_a_new_attempt(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    await task_repository.release(claim)

    requeued = await task_repository.claim("archive-1", claim.task.url_key)

    assert requeued == replace(claim, attempt_id="attempt-2", fence=2)


async def test_complete_emits_page_captured(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    outbox_repository: OutboxRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    await task_repository.complete(outcome_for(claim))

    message = await claim_outbox_message(outbox_repository, PAGE_CAPTURED_EVENT)

    assert json.loads(message.envelope) == {
        "messageId": str(uuid5(NAMESPACE_URL, "page-captured:archive-1:snapshot-1")),
        "correlationId": "archive-1",
        "type": PAGE_CAPTURED_EVENT,
        "version": 1,
        "occurredAt": "2027-01-15T08:00:00Z",
        "payload": {
            "archiveId": "archive-1",
            "snapshotId": "snapshot-1",
            "urlKey": claim.task.url_key,
            "url": claim.task.url,
            "finalUrl": claim.task.url,
            "redirectChain": [],
            "capturedAt": "2027-01-15T08:00:00Z",
            "warcArtifacts": [
                {
                    "bucket": WARC_ARTIFACT.bucket,
                    "key": WARC_ARTIFACT.key,
                    "sha256": WARC_ARTIFACT.sha256,
                    "sizeBytes": WARC_ARTIFACT.size_bytes,
                }
            ],
        },
    }


async def test_complete_admits_discovered_pages(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)
    discovered_url = "https://example.org/next"

    assert claim is not None

    await task_repository.admit_discovered(claim, (discovered_url,))

    identity = identify_url(discovered_url)
    discovered = await task_repository.claim("archive-1", identity.url_key)

    assert discovered == TaskClaim(
        task=PageTask(
            archive_id="archive-1",
            url_key=identity.url_key,
            url=identity.navigation_url,
            depth=1,
        ),
        attempt_id="attempt-2",
        fence=1,
        lease_until=1_800_000_060.0,
    )


async def test_complete_rejects_a_stale_claim(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    await task_repository.release(claim)

    with pytest.raises(TaskClaimLostError):
        await task_repository.complete(outcome_for(claim))


async def test_complete_rejects_a_changed_auth_generation(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    session_store: SessionStore,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    await session_store.reserve_generation("archive-1")

    with pytest.raises(AuthGenerationChanged):
        await task_repository.complete(outcome_for(claim))


async def test_fail_marks_the_task_as_failed(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    await task_repository.fail(claim, "capture_failed", "capture failed")

    assert await task_repository.claim("archive-1", claim.task.url_key) is None


async def test_fail_rejects_a_stale_claim(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    await task_repository.release(claim)

    with pytest.raises(TaskClaimLostError):
        await task_repository.fail(claim, "capture_failed", "capture failed")


async def test_admit_discovered_respects_the_page_limit(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=2,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    await task_repository.admit_discovered(
        claim,
        (
            "https://example.org/second",
            "https://example.org/third",
        ),
    )

    second = identify_url("https://example.org/second")
    third = identify_url("https://example.org/third")

    assert await task_repository.claim("archive-1", second.url_key) is not None
    assert await task_repository.claim("archive-1", third.url_key) is None


async def test_admit_discovered_rejects_a_stale_parent_claim(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    await task_repository.release(claim)

    with pytest.raises(TaskClaimLostError):
        await task_repository.admit_discovered(claim, ("https://example.org/next",))


def outcome_for(claim: TaskClaim) -> CaptureOutcome:
    return CaptureOutcome(
        archive_id=claim.task.archive_id,
        url_key=claim.task.url_key,
        attempt_id=claim.attempt_id,
        fence=claim.fence,
        snapshot_id="snapshot-1",
        capture=PageCapture(
            requested_url=claim.task.url,
            final_url=claim.task.url,
            redirect_chain=(),
            status_code=None,
            content_type=None,
            title="",
            captured_at=datetime(2027, 1, 15, 8, tzinfo=UTC),
            discovered_urls=(),
        ),
        warc_artifacts=(WARC_ARTIFACT,),
    )
