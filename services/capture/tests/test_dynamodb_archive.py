from datetime import UTC, datetime

import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.domain import (
    complete_frontier,
    fail_frontier,
    seed_frontier,
    seed_run,
    seed_snapshot,
    set_run_publication,
)
from support.s3 import FakeS3

from adapters.persistence.dynamodb.archive import (
    DynamoDBArchiveRetrieval,
    encode_cursor,
)
from domain import (
    ArchivePage,
    InvalidArchiveCursor,
    InvalidWACZRange,
    SnapshotReference,
    WACZRangeNotSatisfiable,
)
from utils.io import collect


@pytest.mark.integration
async def test_list_pages_returns_pending_page(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_frontier(dynamodb)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    listing = await retrieval.list_pages("archive-1", 25, None)

    assert listing.items == (ArchivePage(url="https://example.org/", status="PENDING"),)
    assert listing.next_cursor is None


@pytest.mark.integration
async def test_list_pages_maps_completed_page_to_captured(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_frontier(dynamodb)
    complete_frontier(dynamodb)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    listing = await retrieval.list_pages("archive-1", 25, None)

    assert listing.items == (
        ArchivePage(
            url="https://example.org/",
            status="CAPTURED",
            snapshot_id="snapshot-1",
            captured_at="2026-11-24T10:00:00Z",
        ),
    )


@pytest.mark.integration
async def test_list_pages_maps_failed_page_with_error_code(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_frontier(dynamodb)
    fail_frontier(dynamodb)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    listing = await retrieval.list_pages("archive-1", 25, None)

    assert listing.items == (
        ArchivePage(
            url="https://example.org/",
            status="FAILED",
            error_code="navigation_failed",
        ),
    )


@pytest.mark.integration
async def test_list_pages_follows_opaque_cursor(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_frontier(dynamodb)

    dynamodb.put_item(
        TableName="capture_frontier",
        Item={
            "archiveId": {"S": "archive-1"},
            "urlKey": {"S": "url-2"},
            "url": {"S": "https://example.org/second"},
            "depth": {"N": "0"},
            "state": {"S": "PENDING"},
        },
    )

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    first = await retrieval.list_pages("archive-1", 1, None)

    assert first.items == (ArchivePage(url="https://example.org/", status="PENDING"),)
    assert first.next_cursor is not None

    second = await retrieval.list_pages("archive-1", 1, first.next_cursor)

    assert second.items == (ArchivePage(url="https://example.org/second", status="PENDING"),)
    assert second.next_cursor is None


@pytest.mark.integration
async def test_list_pages_rejects_cursor_from_another_archive(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_frontier(dynamodb)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    cursor = encode_cursor({"archiveId": {"S": "other"}, "urlKey": {"S": "url-1"}})

    with pytest.raises(InvalidArchiveCursor):
        await retrieval.list_pages("archive-1", 25, cursor)


@pytest.mark.integration
async def test_read_snapshot_returns_contract_metadata(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_snapshot(dynamodb)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    snapshot = await retrieval.read_snapshot("archive-1", "snapshot-1")

    assert snapshot == SnapshotReference(
        archive_id="archive-1",
        snapshot_id="snapshot-1",
        url="https://example.org/",
        final_url="https://example.org/final",
        captured_at="2026-11-24T10:00:00Z",
        content_type="text/html",
    )


@pytest.mark.integration
async def test_read_snapshot_ignores_snapshot_from_another_archive(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_snapshot(dynamodb, archive_id="other")

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    assert await retrieval.read_snapshot("archive-1", "snapshot-1") is None


@pytest.mark.integration
async def test_read_wacz_returns_none_before_publication(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_run(dynamodb)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    assert await retrieval.read_wacz("archive-1", None, None) is None


@pytest.mark.integration
async def test_read_wacz_returns_none_until_replay_is_ready(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_run(dynamodb)
    set_run_publication(dynamodb, replay_status="NOT_READY")

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    assert await retrieval.read_wacz("archive-1", None, None) is None


@pytest.mark.integration
async def test_read_wacz_returns_none_without_a_package_key(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_run(dynamodb)
    set_run_publication(dynamodb)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    assert await retrieval.read_wacz("archive-1", None, None) is None


@pytest.mark.integration
async def test_read_wacz_streams_published_package(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_run(dynamodb)
    set_run_publication(dynamodb, package_key=PACKAGE_KEY)
    put_package(s3)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    result = await retrieval.read_wacz("archive-1", None, None)

    assert result is not None
    assert result.partial is False
    assert result.content_range is None
    assert result.etag == '"package-1"'
    assert result.last_modified == "Tue, 24 Nov 2026 10:00:00 GMT"
    assert await collect(result.body) == b"0123456789"


@pytest.mark.integration
async def test_read_wacz_delivers_requested_range(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_run(dynamodb)
    set_run_publication(dynamodb, package_key=PACKAGE_KEY)
    put_package(s3)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    result = await retrieval.read_wacz("archive-1", "bytes=2-5", None)

    assert result is not None
    assert result.partial is True
    assert result.content_length == 4
    assert result.content_range == "bytes 2-5/10"
    assert await collect(result.body) == b"2345"


@pytest.mark.integration
async def test_read_wacz_delivers_suffix_range(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_run(dynamodb)
    set_run_publication(dynamodb, package_key=PACKAGE_KEY)
    put_package(s3)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    result = await retrieval.read_wacz("archive-1", "bytes=-4", None)

    assert result is not None
    assert result.content_range == "bytes 6-9/10"
    assert await collect(result.body) == b"6789"


@pytest.mark.integration
async def test_read_wacz_ignores_range_with_stale_if_range(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_run(dynamodb)
    set_run_publication(dynamodb, package_key=PACKAGE_KEY)
    put_package(s3)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    result = await retrieval.read_wacz("archive-1", "bytes=0-1", '"stale"')

    assert result is not None
    assert result.partial is False
    assert await collect(result.body) == b"0123456789"


@pytest.mark.integration
async def test_read_wacz_rejects_invalid_range(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_run(dynamodb)
    set_run_publication(dynamodb, package_key=PACKAGE_KEY)
    put_package(s3)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    with pytest.raises(InvalidWACZRange):
        await retrieval.read_wacz("archive-1", "bytes=1-2,4-5", None)


@pytest.mark.integration
async def test_read_wacz_rejects_unsatisfiable_range(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
) -> None:
    seed_run(dynamodb)
    set_run_publication(dynamodb, package_key=PACKAGE_KEY)
    put_package(s3)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket="capture-artifacts",
    )

    with pytest.raises(WACZRangeNotSatisfiable):
        await retrieval.read_wacz("archive-1", "bytes=20-", None)


PACKAGE_KEY = "packages/archive-1.wacz"


def put_package(s3: FakeS3) -> None:
    s3.put_object(
        Bucket="capture-artifacts",
        Key=PACKAGE_KEY,
        Body=b"0123456789",
        ETag='"package-1"',
        LastModified=datetime(2026, 11, 24, 10, 0, tzinfo=UTC),
    )
