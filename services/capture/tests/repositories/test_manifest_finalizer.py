from datetime import UTC, datetime

import pytest

from contracts.messages import CAPTURE_PAGE_EVENT
from domain.capture import (
    ArtifactReference,
    CaptureOutcome,
    CaptureRunMissing,
    PageCapture,
    PendingPackage,
    StartCrawl,
    identify_url,
    manifest_key,
)
from ports.capture import (
    ArchivePublicationRepository,
    CrawlFinalizer,
    CrawlStarter,
    OutboxRepository,
    TaskRepository,
)

pytestmark = pytest.mark.integration


async def test_finalizer_ignores_an_open_crawl(
    crawl_starter: CrawlStarter,
    manifest_finalizer: CrawlFinalizer,
    outbox_repository: OutboxRepository,
) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )

    await manifest_finalizer("archive-1")

    message = await outbox_repository.claim(60.0)

    assert message is not None
    assert message.message_type == CAPTURE_PAGE_EVENT


async def test_finalizer_rejects_an_unknown_crawl(
    manifest_finalizer: CrawlFinalizer,
) -> None:
    with pytest.raises(CaptureRunMissing):
        await manifest_finalizer("archive-1")


async def test_finalizer_publishes_a_failed_seed_manifest(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
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

    await task_repository.fail(claim, "capture_failed", "seed capture failed")
    await manifest_finalizer("archive-1")

    package = await publication_repository.claim_package(60.0)

    assert package is not None
    assert package == PendingPackage(
        archive_id="archive-1",
        manifest_key=manifest_key("archive-1", package.manifest_digest),
        manifest_digest=package.manifest_digest,
        closed_at="2027-01-15T08:00:00Z",
        lease_owner="owner-1",
    )


async def test_finalizer_publishes_a_manifest_for_a_completed_seed(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)
    artifact = ArtifactReference(
        bucket="warcs",
        key="warcs/1.warc.gz",
        sha256="0" * 64,
        size_bytes=10,
    )

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

    await task_repository.complete(
        CaptureOutcome(
            archive_id="archive-1",
            url_key=identity.url_key,
            attempt_id=claim.attempt_id,
            fence=claim.fence,
            snapshot_id="snapshot-1",
            capture=PageCapture(
                requested_url=identity.navigation_url,
                final_url=identity.navigation_url,
                redirect_chain=(),
                status_code=None,
                content_type=None,
                title="",
                captured_at=datetime(2027, 1, 15, 8, 0, tzinfo=UTC),
                discovered_urls=(),
            ),
            warc_artifacts=(artifact,),
        )
    )

    await manifest_finalizer("archive-1")

    package = await publication_repository.claim_package(60.0)

    assert package is not None
    assert package == PendingPackage(
        archive_id="archive-1",
        manifest_key=manifest_key("archive-1", package.manifest_digest),
        manifest_digest=package.manifest_digest,
        closed_at="2027-01-15T08:00:00Z",
        lease_owner="owner-1",
    )
