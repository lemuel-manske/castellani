from dataclasses import replace
from datetime import UTC, datetime
from hashlib import md5
from pathlib import Path

import pytest

from application.capture.archive_retrieval import ArchiveRetrieval
from domain.capture import (
    ArchivePage,
    ArtifactReference,
    CaptureOutcome,
    InvalidPageLimit,
    PageCapture,
    PageListing,
    PreparedPackage,
    PublicationDecision,
    SnapshotReference,
    StartCrawl,
    TaskClaim,
    WACZObject,
    WACZRangeNotSatisfiable,
    identify_url,
)
from ports.artifacts import PackageArtifacts
from ports.capture import (
    ArchivePublicationRepository,
    CrawlFinalizer,
    CrawlStarter,
    TaskRepository,
)

pytestmark = pytest.mark.integration

WACZ_BYTES = b"0123456789"
WACZ_ETAG = f'"{md5(WACZ_BYTES).hexdigest()}"'


async def test_list_pages_returns_the_seeded_page(
    crawl_starter: CrawlStarter,
    archive_retrieval: ArchiveRetrieval,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)
    await start_archive(crawl_starter)

    listing = await archive_retrieval.list_pages("archive-1", 10, None)

    assert listing == PageListing(
        items=(ArchivePage(url=identity.navigation_url, status="PENDING"),),
        next_cursor=None,
    )


async def test_list_pages_paginates_over_discovered_pages(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    archive_retrieval: ArchiveRetrieval,
) -> None:
    seed_url = "https://example.org/"
    discovered_url = "https://example.org/next"
    await start_archive(crawl_starter)
    claim = await task_repository.claim("archive-1", identify_url(seed_url).url_key)

    assert claim is not None

    await task_repository.admit_discovered(claim, (discovered_url,))

    first = await archive_retrieval.list_pages("archive-1", 1, None)

    assert first.next_cursor is not None

    second = await archive_retrieval.list_pages("archive-1", 1, first.next_cursor)

    urls = {item.url for page in (first, second) for item in page.items}

    assert urls == {seed_url, discovered_url}
    assert second.next_cursor is None


async def test_list_pages_rejects_an_invalid_limit(
    archive_retrieval: ArchiveRetrieval,
) -> None:
    with pytest.raises(InvalidPageLimit):
        await archive_retrieval.list_pages("archive-1", 0, None)


async def test_read_snapshot_returns_the_completed_snapshot(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    archive_retrieval: ArchiveRetrieval,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)
    await start_archive(crawl_starter)
    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    await task_repository.complete(outcome_for(claim))

    snapshot = await archive_retrieval.read_snapshot("archive-1", "snapshot-1")

    assert snapshot == SnapshotReference(
        archive_id="archive-1",
        snapshot_id="snapshot-1",
        url=identity.navigation_url,
        final_url=identity.navigation_url,
        captured_at="2027-01-15T08:00:00Z",
        content_type=None,
    )


async def test_read_snapshot_returns_none_for_an_unknown_snapshot(
    archive_retrieval: ArchiveRetrieval,
) -> None:
    assert await archive_retrieval.read_snapshot("archive-1", "missing") is None


async def test_read_wacz_returns_the_published_object(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
    package_artifacts: PackageArtifacts,
    archive_retrieval: ArchiveRetrieval,
    tmp_path: Path,
) -> None:
    await publish_archive(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
        package_artifacts,
        tmp_path,
    )

    wacz = await archive_retrieval.read_wacz("archive-1", None, None)

    assert wacz is not None

    body = await wacz.consume()

    assert replace(wacz, body=None) == WACZObject(
        body=None,
        content_length=len(WACZ_BYTES),
        etag=WACZ_ETAG,
        last_modified=wacz.last_modified,
        content_range=None,
        partial=False,
    )
    assert body == WACZ_BYTES


async def test_read_wacz_returns_metadata_only(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
    package_artifacts: PackageArtifacts,
    archive_retrieval: ArchiveRetrieval,
    tmp_path: Path,
) -> None:
    await publish_archive(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
        package_artifacts,
        tmp_path,
    )

    wacz = await archive_retrieval.read_wacz("archive-1", None, None, metadata_only=True)

    assert wacz is not None
    assert wacz == WACZObject(
        body=None,
        content_length=len(WACZ_BYTES),
        etag=WACZ_ETAG,
        last_modified=wacz.last_modified,
        content_range=None,
        partial=False,
    )


async def test_read_wacz_returns_a_byte_range(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
    package_artifacts: PackageArtifacts,
    archive_retrieval: ArchiveRetrieval,
    tmp_path: Path,
) -> None:
    await publish_archive(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
        package_artifacts,
        tmp_path,
    )

    wacz = await archive_retrieval.read_wacz("archive-1", "bytes=2-5", None)

    assert wacz is not None

    body = await wacz.consume()

    assert replace(wacz, body=None) == WACZObject(
        body=None,
        content_length=4,
        etag=WACZ_ETAG,
        last_modified=wacz.last_modified,
        content_range="bytes 2-5/10",
        partial=True,
    )
    assert body == WACZ_BYTES[2:6]


async def test_read_wacz_honors_a_matching_if_range(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
    package_artifacts: PackageArtifacts,
    archive_retrieval: ArchiveRetrieval,
    tmp_path: Path,
) -> None:
    await publish_archive(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
        package_artifacts,
        tmp_path,
    )

    wacz = await archive_retrieval.read_wacz("archive-1", "bytes=0-2", WACZ_ETAG)

    assert wacz is not None
    assert wacz.content_range == "bytes 0-2/10"


async def test_read_wacz_ignores_a_range_with_a_stale_if_range(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
    package_artifacts: PackageArtifacts,
    archive_retrieval: ArchiveRetrieval,
    tmp_path: Path,
) -> None:
    await publish_archive(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
        package_artifacts,
        tmp_path,
    )

    wacz = await archive_retrieval.read_wacz("archive-1", "bytes=0-2", '"stale"')

    assert wacz is not None
    assert wacz.content_range is None


async def test_read_wacz_rejects_an_unsatisfiable_range(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
    package_artifacts: PackageArtifacts,
    archive_retrieval: ArchiveRetrieval,
    tmp_path: Path,
) -> None:
    await publish_archive(
        crawl_starter,
        task_repository,
        manifest_finalizer,
        publication_repository,
        package_artifacts,
        tmp_path,
    )

    with pytest.raises(WACZRangeNotSatisfiable) as raised:
        await archive_retrieval.read_wacz("archive-1", "bytes=20-25", None)

    assert raised.value.content_length == len(WACZ_BYTES)


async def test_read_wacz_returns_none_before_publication(
    crawl_starter: CrawlStarter,
    archive_retrieval: ArchiveRetrieval,
) -> None:
    await start_archive(crawl_starter)

    assert await archive_retrieval.read_wacz("archive-1", None, None) is None


async def test_read_wacz_returns_none_for_an_unknown_archive(
    archive_retrieval: ArchiveRetrieval,
) -> None:
    assert await archive_retrieval.read_wacz("missing", None, None) is None


async def start_archive(crawl_starter: CrawlStarter) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )


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
        warc_artifacts=(
            ArtifactReference(
                bucket="warcs",
                key="warcs/seed.warc.gz",
                sha256="0" * 64,
                size_bytes=10,
            ),
        ),
    )


async def publish_archive(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
    manifest_finalizer: CrawlFinalizer,
    publication_repository: ArchivePublicationRepository,
    package_artifacts: PackageArtifacts,
    tmp_path: Path,
) -> ArtifactReference:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)
    await start_archive(crawl_starter)
    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim is not None

    await task_repository.complete(outcome_for(claim))
    await manifest_finalizer("archive-1")

    package = await publication_repository.claim_package(60.0)

    assert package is not None

    path = tmp_path / "archive.wacz"
    path.write_bytes(WACZ_BYTES)
    artifact = await package_artifacts.persist_package(path, "archive-1", package.manifest_digest)

    await publication_repository.prepare(
        PreparedPackage(
            archive_id="archive-1",
            artifact=artifact,
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
            package_digest=artifact.sha256,
            occurred_at="2027-01-15T10:00:00Z",
        )
    )

    return artifact
