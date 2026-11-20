import json
from collections.abc import Awaitable, Callable
from typing import cast

from aio_pika.abc import AbstractIncomingMessage

EXPECTED_MESSAGE_TYPE = "CapturePage"
EXPECTED_MESSAGE_VERSION = 1


def parse_delivery(body: bytes) -> tuple[str, str] | None:
    try:
        decoded: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(decoded, dict):
        return None

    envelope = cast(dict[str, object], decoded)

    if envelope.get("type") != EXPECTED_MESSAGE_TYPE or envelope.get("version") != EXPECTED_MESSAGE_VERSION:
        return None

    payload = envelope.get("payload")

    if not isinstance(payload, dict):
        return None

    payload = cast(dict[str, object], payload)

    archive_id = payload.get("archiveId")
    url_key = payload.get("urlKey")

    if not isinstance(archive_id, str) or not archive_id:
        return None

    if not isinstance(url_key, str) or not url_key:
        return None

    return archive_id, url_key


class RabbitMQPageTaskConsumer:
    """Translates CapturePage deliveries into page-capture use-case calls."""

    def __init__(
        self,
        process_page: Callable[[str, str], Awaitable[bool]],
    ) -> None:
        self.process_page = process_page

    async def handle(self, message: AbstractIncomingMessage) -> None:
        delivery = parse_delivery(message.body)

        if delivery is None:
            await message.reject(requeue=False)
            return

        archive_id, url_key = delivery

        async with message.process(requeue=True):
            await self.process_page(archive_id, url_key)
