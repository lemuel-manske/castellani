from dataclasses import dataclass
from typing import Protocol


class OutboxLeaseLostError(RuntimeError):
    """Raised when an outbox message is no longer owned by this dispatcher."""


@dataclass(frozen=True)
class OutboxMessage:
    """A durable message claimed for publication."""

    message_id: str
    message_type: str
    envelope: bytes
    lease_token: str


class OutboxRepository(Protocol):
    """Claims and records delivery of durable outbox messages."""

    async def claim(self, lease_duration: float) -> OutboxMessage | None: ...

    async def confirm(self, message: OutboxMessage) -> None: ...

    async def reschedule(self, message: OutboxMessage, delay: float) -> None: ...
