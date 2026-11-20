import json
from typing import Any

import pytest

from adapters.messaging.rabbitmq.consumer import RabbitMQPageTaskConsumer


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


async def test_consumer_processes_a_valid_capture_page_delivery() -> None:
    processed: list[tuple[str, str]] = []

    async def process_page(archive_id: str, url_key: str) -> bool:
        processed.append((archive_id, url_key))
        return True

    message = IncomingMessage(capture_page_envelope())
    consumer = RabbitMQPageTaskConsumer(process_page)

    await consumer.handle(message)  # type: ignore[arg-type]

    assert processed == [("archive-1", "url-1")]
    assert message.process_context.acknowledged
    assert not message.rejected


async def test_consumer_rejects_malformed_deliveries_without_requeue() -> None:
    async def process_page(archive_id: str, url_key: str) -> bool:
        pytest.fail("Malformed deliveries must not reach the application")

    message = IncomingMessage(b"not-json")
    consumer = RabbitMQPageTaskConsumer(process_page)

    await consumer.handle(message)  # type: ignore[arg-type]

    assert message.rejected
    assert not message.requeue_on_process


async def test_consumer_requeues_when_the_application_cannot_process_delivery() -> None:
    async def process_page(archive_id: str, url_key: str) -> bool:
        raise RuntimeError("task state unavailable")

    message = IncomingMessage(capture_page_envelope())
    consumer = RabbitMQPageTaskConsumer(process_page)

    with pytest.raises(RuntimeError, match="task state unavailable"):
        await consumer.handle(message)  # type: ignore[arg-type]

    assert not message.process_context.acknowledged
    assert message.process_context.requeued
    assert message.requeue_on_process
