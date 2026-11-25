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
