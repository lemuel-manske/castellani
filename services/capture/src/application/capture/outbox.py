import asyncio
import logging

from ports.capture import OutboxRepository
from ports.messaging import MessagePublisher

logger = logging.getLogger(__name__)


DEFAULT_LEASE_DURATION = 30.0
DEFAULT_RETRY_DELAY = 5.0
DEFAULT_POLL_INTERVAL = 0.5


class OutboxDispatcher:
    """Delivers durable outbox messages and records their publication outcome."""

    def __init__(
        self,
        outbox: OutboxRepository,
        publisher: MessagePublisher,
        lease_duration: float = DEFAULT_LEASE_DURATION,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        if lease_duration <= 0:
            raise ValueError("lease_duration must be positive")

        if retry_delay <= 0:
            raise ValueError("retry_delay must be positive")

        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")

        self.outbox = outbox
        self.publisher = publisher

        self.lease_duration = lease_duration
        self.retry_delay = retry_delay
        self.poll_interval = poll_interval

    async def run(self) -> None:
        while True:
            try:
                dispatched = await self._dispatch_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("outbox dispatch cycle failed")
                dispatched = False

            if not dispatched:
                await asyncio.sleep(self.poll_interval)

    async def _dispatch_once(self) -> bool:
        message = await self.outbox.claim(self.lease_duration)

        if message is None:
            return False

        try:
            await self.publisher.publish(
                message.message_id,
                message.message_type,
                message.envelope,
            )
        except Exception:
            logger.exception("failed to publish outbox message %s", message.message_id)

            await self.outbox.reschedule(message, self.retry_delay)

            return True

        await self.outbox.confirm(message)

        return True
