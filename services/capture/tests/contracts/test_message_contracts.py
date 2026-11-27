import json

from contracts.messages import (
    ARCHIVE_COMPENSATED_EVENT,
    ARCHIVE_COMPENSATION_DECIDED_EVENT,
    ARCHIVE_PREPARED_EVENT,
    ARCHIVE_PUBLICATION_DECIDED_EVENT,
    ARCHIVE_PUBLISHED_EVENT,
    CAPTURE_PAGE_EVENT,
    CRAWL_COMPLETED_EVENT,
    PAGE_CAPTURED_EVENT,
    START_CRAWL_EVENT,
    ArchiveCompensatedPayload,
    ArchiveCompensationDecidedPayload,
    ArchivePreparedPayload,
    ArchivePublicationDecidedPayload,
    ArchivePublishedPayload,
    CapturePagePayload,
    CrawlCompletedPayload,
    PageCapturedPayload,
    StartCrawlPayload,
)
from contracts.validation import validate_message

MESSAGE_CONTRACTS = (
    ("capture-page.v1.schema.json", CAPTURE_PAGE_EVENT, CapturePagePayload),
    ("start-crawl.v1.schema.json", START_CRAWL_EVENT, StartCrawlPayload),
    (
        "archive-publication-decided.v1.schema.json",
        ARCHIVE_PUBLICATION_DECIDED_EVENT,
        ArchivePublicationDecidedPayload,
    ),
    (
        "archive-compensation-decided.v1.schema.json",
        ARCHIVE_COMPENSATION_DECIDED_EVENT,
        ArchiveCompensationDecidedPayload,
    ),
    ("page-captured.v1.schema.json", PAGE_CAPTURED_EVENT, PageCapturedPayload),
    ("crawl-completed.v1.schema.json", CRAWL_COMPLETED_EVENT, CrawlCompletedPayload),
    ("archive-prepared.v1.schema.json", ARCHIVE_PREPARED_EVENT, ArchivePreparedPayload),
    ("archive-published.v1.schema.json", ARCHIVE_PUBLISHED_EVENT, ArchivePublishedPayload),
    (
        "archive-compensated.v1.schema.json",
        ARCHIVE_COMPENSATED_EVENT,
        ArchiveCompensatedPayload,
    ),
)


def test_message_contracts_validate_capture_page_from_contract() -> None:
    envelope = {
        "messageId": "message-1",
        "correlationId": "archive-1",
        "type": "CapturePage",
        "version": 1,
        "occurredAt": "2026-11-20T12:00:00Z",
        "payload": {"archiveId": "archive-1", "urlKey": "v1-identity"},
    }

    assert validate_message(json.dumps(envelope).encode(), "CapturePage") == envelope


def test_message_contracts_reject_boolean_version() -> None:
    envelope = {
        "messageId": "message-1",
        "correlationId": "archive-1",
        "type": "CapturePage",
        "version": True,
        "occurredAt": "2026-11-20T12:00:00Z",
        "payload": {"archiveId": "archive-1", "urlKey": "url-1"},
    }

    assert validate_message(json.dumps(envelope).encode(), "CapturePage") is None


def test_message_contracts_validate_start_crawl_from_contract() -> None:
    envelope = {
        "messageId": "message-start",
        "correlationId": "archive-start",
        "type": "StartCrawl",
        "version": 1,
        "occurredAt": "2026-11-25T12:00:00Z",
        "payload": {
            "archiveId": "archive-start",
            "seedUrl": "https://example.org/",
            "maxDepth": 2,
            "maxPages": 5,
            "authGeneration": 3,
            "normalizerVersion": "v1",
        },
    }

    assert validate_message(json.dumps(envelope).encode(), "StartCrawl") == envelope


def test_message_contracts_validate_crawl_completed_with_shared_manifest_ref() -> None:
    key = (
        "manifests/archive-1/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json"
    )

    envelope = {
        "messageId": "message-completed",
        "correlationId": "archive-1",
        "type": "CrawlCompleted",
        "version": 1,
        "occurredAt": "2026-11-25T12:00:00Z",
        "payload": {
            "archiveId": "archive-1",
            "manifest": {
                "bucket": "castellani-archive-manifests",
                "key": key,
                "sha256": "a" * 64,
                "sizeBytes": 128,
                "versionId": "legacy-version",
            },
            "manifestDigest": "a" * 64,
            "seedSucceeded": True,
            "capturedCount": 1,
            "failedCount": 0,
        },
    }

    assert validate_message(json.dumps(envelope).encode(), "CrawlCompleted") == envelope
