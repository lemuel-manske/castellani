from capture.serialization import (
    archive_page_json,
    page_listing_json,
    snapshot_reference_json,
)
from domain.capture import ArchivePage, PageListing, SnapshotReference


def test_archive_page_json_omits_unset_fields() -> None:
    page = ArchivePage("https://example.org/", "PENDING")

    assert archive_page_json(page) == {
        "url": "https://example.org/",
        "status": "PENDING",
    }


def test_page_listing_json_includes_pages_and_cursor() -> None:
    listing = PageListing(
        items=(
            ArchivePage(
                "https://example.org/",
                "CAPTURED",
                snapshot_id="snapshot-1",
                captured_at="2026-11-24T00:00:00Z",
            ),
        ),
        next_cursor="cursor-1",
    )

    assert page_listing_json(listing) == {
        "items": [
            {
                "url": "https://example.org/",
                "status": "CAPTURED",
                "snapshotId": "snapshot-1",
                "capturedAt": "2026-11-24T00:00:00Z",
            },
        ],
        "nextCursor": "cursor-1",
    }


def test_snapshot_reference_json_includes_optional_fields() -> None:
    snapshot = SnapshotReference(
        archive_id="archive-1",
        snapshot_id="snapshot-1",
        url="https://example.org/",
        final_url="https://example.org/final",
        captured_at="2026-11-24T00:00:00Z",
        content_type="text/html",
    )

    assert snapshot_reference_json(snapshot) == {
        "archiveId": "archive-1",
        "snapshotId": "snapshot-1",
        "url": "https://example.org/",
        "finalUrl": "https://example.org/final",
        "capturedAt": "2026-11-24T00:00:00Z",
        "contentType": "text/html",
    }
