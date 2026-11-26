from typing import Generic, Literal, TypedDict, TypeVar

Payload = TypeVar("Payload")


class Envelope(TypedDict, Generic[Payload]):
    messageId: str
    correlationId: str
    type: str
    version: Literal[1]
    occurredAt: str
    payload: Payload
