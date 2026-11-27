from dataclasses import dataclass


class OutboxLeaseLostError(RuntimeError):
    """Raised when an outbox message is no longer owned by this dispatcher."""


class InvalidRescheduleDelay(ValueError):
    """Raised when an outbox message is rescheduled with a negative delay."""


@dataclass(frozen=True)
class OutboxMessage:
    """A durable message claimed for publication."""

    message_id: str
    message_type: str
    envelope: bytes
    lease_token: str
