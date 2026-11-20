import pytest

from adapters.messaging.rabbitmq.consumer import RabbitMQPageTaskConsumer
from support.rabbitmq import IncomingMessage, capture_page_envelope


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
