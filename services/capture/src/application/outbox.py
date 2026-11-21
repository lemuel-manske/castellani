from typing import Protocol

from domain import OutboxMessage


class MessagePublisher(Protocol):
    """Publishes an immutable message envelope to the broker."""

    async def publish(self, message: OutboxMessage) -> None: ...
