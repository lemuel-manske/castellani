import json

from adapters.messaging.contracts import validate_message


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
                "key": "manifests/archive-1/manifest.json",
                "sha256": "a" * 64,
                "sizeBytes": 128,
                "versionId": "version-1",
            },
            "manifestDigest": "a" * 64,
            "seedSucceeded": True,
            "capturedCount": 1,
            "failedCount": 0,
        },
    }

    assert validate_message(json.dumps(envelope).encode(), "CrawlCompleted") == envelope
