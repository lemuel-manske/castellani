import json
from collections.abc import Awaitable, Callable
from typing import Any

from aio_pika.abc import AbstractIncomingMessage


class RabbitMQPageTaskConsumer:
    """Translates CapturePage deliveries into page-capture use-case calls."""

    def __init__(
        self,
        process_page: Callable[[str, str], Awaitable[bool]],
    ) -> None:
        self.process_page = process_page

    async def handle(self, message: AbstractIncomingMessage) -> None:
        delivery = self._parse_delivery(message.body)

        if delivery is None:
            await message.reject(requeue=False)
            return

        archive_id, url_key = delivery

        async with message.process(requeue=True):
            await self.process_page(archive_id, url_key)

    @staticmethod
    def _parse_delivery(body: bytes) -> tuple[str, str] | None:
        try:
            envelope: Any = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

        if not isinstance(envelope, dict):
            return None

        if envelope.get("type") != "CapturePage" or envelope.get("version") != 1:
            return None

        payload = envelope.get("payload")

        if not isinstance(payload, dict):
            return None

        archive_id = payload.get("archiveId")
        url_key = payload.get("urlKey")

        if not isinstance(archive_id, str) or not archive_id:
            return None

        if not isinstance(url_key, str) or not url_key:
            return None

        return archive_id, url_key
