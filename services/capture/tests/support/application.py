from domain.capture import OutboxMessage
from utils.fn import noop


class FakeOutbox:
    def __init__(self, message: OutboxMessage | None) -> None:
        self.message = message
        self.confirmed: list[OutboxMessage] = []
        self.rescheduled: list[tuple[OutboxMessage, float]] = []

    async def claim(self, lease_duration: float) -> OutboxMessage | None:
        noop(lease_duration)

        return self.message

    async def confirm(self, message: OutboxMessage) -> None:
        self.confirmed.append(message)

    async def reschedule(self, message: OutboxMessage, delay: float) -> None:
        self.rescheduled.append((message, delay))


class FailingOutbox(FakeOutbox):
    async def confirm(self, message: OutboxMessage) -> None:
        noop(message)

        raise RuntimeError("DynamoDB unavailable")


class FakePublisher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, message_id: str, envelope: bytes) -> None:
        self.published.append((message_id, envelope))

        if self.error is not None:
            raise self.error
