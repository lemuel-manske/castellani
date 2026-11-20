import json
from typing import Any


class MessageProcess:
    def __init__(self) -> None:
        self.acknowledged = False
        self.requeued = False

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, error_type: Any, error: Any, traceback: Any) -> None:
        self.acknowledged = error_type is None
        self.requeued = error_type is not None


class IncomingMessage:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.process_context = MessageProcess()
        self.rejected = False
        self.requeue_on_process = False

    def process(self, requeue: bool) -> MessageProcess:
        self.requeue_on_process = requeue
        return self.process_context

    async def reject(self, requeue: bool) -> None:
        self.rejected = True
        self.requeue_on_process = requeue


def capture_page_envelope() -> bytes:
    return json.dumps(
        {
            "messageId": "message-1",
            "correlationId": "correlation-1",
            "type": "CapturePage",
            "version": 1,
            "occurredAt": "2026-11-20T12:00:00Z",
            "payload": {
                "archiveId": "archive-1",
                "urlKey": "url-1",
            },
        }
    ).encode()
