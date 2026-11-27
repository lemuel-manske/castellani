import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from support.clock import SimpleClock
from support.fn import claim_outbox_message

from contracts.messages import (
    ARCHIVE_COMPENSATED_EVENT,
    ARCHIVE_PREPARED_EVENT,
    ARCHIVE_PUBLISHED_EVENT,
)
from domain.capture import (
    ArtifactReference,
    CaptureOutcome,
    CompensationDecision,
    InvalidArchiveDecision,
    InvalidLeaseDuration,
    PackageCommitRejected,
    PageCapture,
    PendingPackage,
    PreparedPackage,
    PublicationDecision,
    StartCrawl,
    archive_compensated_message_id,
    archive_prepared_message_id,
    archive_published_message_id,
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

WARC_ARTIFACT = ArtifactReference(
    bucket="warcs",
    key="warcs/seed.warc.gz",
    sha256="1" * 64,
    size_bytes=10,
)
PACKAGE_ARTIFACT = ArtifactReference(
    bucket="packages",
    key="packages/archive-1.wacz",
    sha256="2" * 64,
    size_bytes=20,
)


async def test_claim_package_returns_the_fenced_pending_package(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
) -> None:
    package = await claim_pending_package(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
    )

    assert package == PendingPackage(
        archive_id="archive-1",
        manifest_key=manifest_key("archive-1", package.manifest_digest),
        manifest_digest=package.manifest_digest,
        closed_at="2027-01-15T08:00:00Z",
        lease_owner="owner-1",
    )


async def test_claim_package_ignores_an_active_lease(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
) -> None:
    await claim_pending_package(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
    )

    assert await publication_repository.claim_package(60.0) is None


async def test_claim_package_reclaims_after_the_lease_expires(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
    clock: SimpleClock,
) -> None:
    package = await claim_pending_package(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
    )

    clock.advance(61.0)

    reclaimed = await publication_repository.claim_package(60.0)

    assert reclaimed == replace(package, lease_owner="owner-2")


async def test_release_package_makes_the_package_claimable_again(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
) -> None:
    package = await claim_pending_package(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
    )

    await publication_repository.release_package(package)

    released = await publication_repository.claim_package(60.0)

    assert released == replace(package, lease_owner="owner-2")


async def test_prepare_commits_the_package_and_emits_archive_prepared(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
    outbox_repository: OutboxRepository,
) -> None:
    package = await claim_pending_package(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
    )

    await publication_repository.prepare(
        PreparedPackage(
            archive_id="archive-1",
            artifact=PACKAGE_ARTIFACT,
            manifest_digest=package.manifest_digest,
            occurred_at="2027-01-15T09:00:00Z",
            lease_owner=package.lease_owner,
        )
    )

    message = await claim_outbox_message(outbox_repository, ARCHIVE_PREPARED_EVENT)

    assert json.loads(message.envelope) == {
        "messageId": archive_prepared_message_id("archive-1", package.manifest_digest),
        "correlationId": "archive-1",
        "type": ARCHIVE_PREPARED_EVENT,
        "version": 1,
        "occurredAt": "2027-01-15T09:00:00Z",
        "payload": {
            "archiveId": "archive-1",
            "package": {
                "bucket": PACKAGE_ARTIFACT.bucket,
                "key": PACKAGE_ARTIFACT.key,
                "sha256": PACKAGE_ARTIFACT.sha256,
                "sizeBytes": PACKAGE_ARTIFACT.size_bytes,
            },
            "packageDigest": PACKAGE_ARTIFACT.sha256,
            "manifestDigest": package.manifest_digest,
        },
    }


async def test_prepare_accepts_a_replay(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
) -> None:
    package = await claim_pending_package(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
    )
    prepared = PreparedPackage(
        archive_id="archive-1",
        artifact=PACKAGE_ARTIFACT,
        manifest_digest=package.manifest_digest,
        occurred_at="2027-01-15T09:00:00Z",
        lease_owner=package.lease_owner,
    )

    await publication_repository.prepare(prepared)
    await publication_repository.prepare(prepared)

    assert await publication_repository.claim_package(60.0) is None


async def test_prepare_rejects_a_stale_lease_owner(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
) -> None:
    package = await claim_pending_package(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
    )
    prepared = PreparedPackage(
        archive_id="archive-1",
        artifact=PACKAGE_ARTIFACT,
        manifest_digest=package.manifest_digest,
        occurred_at="2027-01-15T09:00:00Z",
        lease_owner="owner-2",
    )

    with pytest.raises(PackageCommitRejected):
        await publication_repository.prepare(prepared)


async def test_accept_publication_emits_archive_published(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
    outbox_repository: OutboxRepository,
) -> None:
    package = await claim_pending_package(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
    )
    await publication_repository.prepare(
        PreparedPackage(
            archive_id="archive-1",
            artifact=PACKAGE_ARTIFACT,
            manifest_digest=package.manifest_digest,
            occurred_at="2027-01-15T09:00:00Z",
            lease_owner=package.lease_owner,
        )
    )

    decision = PublicationDecision(
        archive_id="archive-1",
        correlation_id="coordinator-1",
        decision_version=1,
        package_digest=PACKAGE_ARTIFACT.sha256,
        occurred_at="2027-01-15T10:00:00Z",
    )

    await publication_repository.accept_publication(decision)

    message = await claim_outbox_message(outbox_repository, ARCHIVE_PUBLISHED_EVENT)

    assert json.loads(message.envelope) == {
        "messageId": archive_published_message_id("archive-1", 1),
        "correlationId": "archive-1",
        "type": ARCHIVE_PUBLISHED_EVENT,
        "version": 1,
        "occurredAt": "2027-01-15T10:00:00Z",
        "payload": {
            "archiveId": "archive-1",
            "decisionVersion": 1,
            "packageDigest": PACKAGE_ARTIFACT.sha256,
        },
    }


async def test_accept_publication_rejects_a_conflicting_digest(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
) -> None:
    package = await claim_pending_package(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
    )
    await publication_repository.prepare(
        PreparedPackage(
            archive_id="archive-1",
            artifact=PACKAGE_ARTIFACT,
            manifest_digest=package.manifest_digest,
            occurred_at="2027-01-15T09:00:00Z",
            lease_owner=package.lease_owner,
        )
    )
    await publication_repository.accept_publication(
        PublicationDecision(
            archive_id="archive-1",
            correlation_id="coordinator-1",
            decision_version=1,
            package_digest=PACKAGE_ARTIFACT.sha256,
            occurred_at="2027-01-15T10:00:00Z",
        )
    )

    with pytest.raises(InvalidArchiveDecision):
        await publication_repository.accept_publication(
            PublicationDecision(
                archive_id="archive-1",
                correlation_id="coordinator-2",
                decision_version=1,
                package_digest="3" * 64,
                occurred_at="2027-01-15T11:00:00Z",
            )
        )


async def test_compensation_emits_archive_compensated(
    crawl_starter: CrawlStarter,
    publication_repository: ArchivePublicationRepository,
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
    decision = CompensationDecision(
        archive_id="archive-1",
        correlation_id="coordinator-1",
        decision_version=1,
        reason_code="rejected",
        occurred_at="2027-01-15T10:00:00Z",
    )

    await publication_repository.begin_compensation(decision)
    await publication_repository.complete_compensation(decision)

    message = await claim_outbox_message(outbox_repository, ARCHIVE_COMPENSATED_EVENT)

    assert json.loads(message.envelope) == {
        "messageId": archive_compensated_message_id("archive-1", 1),
        "correlationId": "archive-1",
        "type": ARCHIVE_COMPENSATED_EVENT,
        "version": 1,
        "occurredAt": "2027-01-15T10:00:00Z",
        "payload": {
            "archiveId": "archive-1",
            "decisionVersion": 1,
        },
    }


async def test_compensation_rejects_a_conflicting_publication(
    crawl_starter: CrawlStarter,
    publication_repository: ArchivePublicationRepository,
) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )
    await publication_repository.begin_compensation(
        CompensationDecision(
            archive_id="archive-1",
            correlation_id="coordinator-1",
            decision_version=1,
            reason_code="rejected",
            occurred_at="2027-01-15T10:00:00Z",
        )
    )

    with pytest.raises(InvalidArchiveDecision):
        await publication_repository.accept_publication(
            PublicationDecision(
                archive_id="archive-1",
                correlation_id="coordinator-2",
                decision_version=2,
                package_digest=PACKAGE_ARTIFACT.sha256,
                occurred_at="2027-01-15T11:00:00Z",
            )
        )


async def test_claim_package_rejects_a_nonpositive_lease(
    publication_repository: ArchivePublicationRepository,
) -> None:
    with pytest.raises(InvalidLeaseDuration):
        await publication_repository.claim_package(0.0)


async def claim_pending_package(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
) -> PendingPackage:
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
                captured_at=datetime(2027, 1, 15, 8, tzinfo=UTC),
                discovered_urls=(),
            ),
            warc_artifacts=(WARC_ARTIFACT,),
        )
    )

    await manifest_finalizer("archive-1")

    package = await publication_repository.claim_package(60.0)

    assert package is not None

    return package
