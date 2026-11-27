from domain.capture import OutboxMessage
from ports.capture import OutboxRepository


async def claim_outbox_message(
    outbox_repository: OutboxRepository,
    message_type: str,
) -> OutboxMessage:
    while True:
        message = await outbox_repository.claim(60.0)

        assert message is not None

        if message.message_type == message_type:
            return message

        await outbox_repository.confirm(message)
