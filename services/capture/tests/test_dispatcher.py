import pytest
from support.application import FailingOutbox, FakeOutbox, FakePublisher

from application.capture import OutboxDispatcher
from domain.capture import OutboxMessage


@pytest.fixture
def message() -> OutboxMessage:
    return OutboxMessage("message-1", b'{"type":"CapturePage"}', "lease-1")


async def test_dispatcher_publishes_then_confirms_a_claimed_message(
    message: OutboxMessage,
) -> None:
    outbox = FakeOutbox(message)

    publisher = FakePublisher()

    dispatcher = OutboxDispatcher(outbox, publisher)

    assert await dispatcher.dispatch_once()

    assert publisher.published == [(message.message_id, message.envelope)]
    assert outbox.confirmed == [message]
    assert outbox.rescheduled == []


async def test_dispatcher_reschedules_a_message_when_publication_fails(
    message: OutboxMessage,
) -> None:
    outbox = FakeOutbox(message)

    publisher = FakePublisher(ConnectionError())

    dispatcher = OutboxDispatcher(outbox, publisher, retry_delay=12)

    assert await dispatcher.dispatch_once()

    assert publisher.published == [(message.message_id, message.envelope)]
    assert outbox.confirmed == []
    assert outbox.rescheduled == [(message, 12)]


async def test_dispatcher_returns_false_when_no_message_is_due() -> None:
    outbox = FakeOutbox(None)

    publisher = FakePublisher()

    dispatcher = OutboxDispatcher(outbox, publisher)

    assert not await dispatcher.dispatch_once()

    assert publisher.published == []
    assert outbox.confirmed == []
    assert outbox.rescheduled == []


async def test_dispatcher_does_not_confirm_when_persistence_confirmation_fails(
    message: OutboxMessage,
) -> None:
    outbox = FailingOutbox(message)

    publisher = FakePublisher()

    dispatcher = OutboxDispatcher(outbox, publisher)

    with pytest.raises(RuntimeError, match="DynamoDB unavailable"):
        await dispatcher.dispatch_once()

    assert publisher.published == [(message.message_id, message.envelope)]
    assert outbox.rescheduled == []
