import json
from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

import pytest
from support.clock import SimpleClock

from contracts.messages import CAPTURE_PAGE_EVENT
from domain.capture import (
    InvalidLeaseDuration,
    InvalidRescheduleDelay,
    OutboxLeaseLostError,
    OutboxMessage,
    StartCrawl,
    identify_url,
)
from ports.capture import CrawlStarter, OutboxRepository

pytestmark = pytest.mark.integration


async def test_claim_returns_the_seeded_capture_page_message(
    crawl_starter: CrawlStarter,
    outbox_repository: OutboxRepository,
) -> None:
    seed_url = "https://example.org/"
    identity = identify_url(seed_url)

    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url=seed_url,
            max_depth=1,
            max_pages=10,
        )
    )

    message = await outbox_repository.claim(60.0)

    message_id = str(uuid5(NAMESPACE_URL, f"capture-page:archive-1:{identity.url_key}"))

    envelope = {
        "messageId": message_id,
        "correlationId": "archive-1",
        "type": CAPTURE_PAGE_EVENT,
        "version": 1,
        "occurredAt": "2027-01-15T08:00:00Z",
        "payload": {"archiveId": "archive-1", "urlKey": identity.url_key},
    }

    assert message == OutboxMessage(
        message_id=message_id,
        message_type=CAPTURE_PAGE_EVENT,
        envelope=json.dumps(envelope, separators=(",", ":")).encode(),
        lease_token="lease-1",
    )


async def test_claim_returns_none_when_no_message_is_due(
    outbox_repository: OutboxRepository,
) -> None:
    assert await outbox_repository.claim(60.0) is None


async def test_confirm_prevents_reclaiming_the_message(
    crawl_starter: CrawlStarter,
    outbox_repository: OutboxRepository,
) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )

    message = await outbox_repository.claim(60.0)

    assert message is not None

    await outbox_repository.confirm(message)

    assert await outbox_repository.claim(60.0) is None


async def test_reschedule_delays_the_message(
    crawl_starter: CrawlStarter,
    outbox_repository: OutboxRepository,
    clock: SimpleClock,
) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )

    message = await outbox_repository.claim(60.0)

    assert message is not None

    await outbox_repository.reschedule(message, 5.0)

    assert await outbox_repository.claim(60.0) is None

    clock.advance(5.0)

    reclaimed = await outbox_repository.claim(60.0)

    assert reclaimed == replace(message, lease_token="lease-2")


async def test_confirm_rejects_a_stale_lease(
    crawl_starter: CrawlStarter,
    outbox_repository: OutboxRepository,
    clock: SimpleClock,
) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )

    message = await outbox_repository.claim(60.0)

    assert message is not None

    clock.advance(60.0)

    reclaimed = await outbox_repository.claim(60.0)

    assert reclaimed is not None

    with pytest.raises(OutboxLeaseLostError):
        await outbox_repository.confirm(message)


async def test_claim_rejects_a_nonpositive_lease(
    outbox_repository: OutboxRepository,
) -> None:
    with pytest.raises(InvalidLeaseDuration):
        await outbox_repository.claim(0.0)


async def test_reschedule_rejects_a_negative_delay(
    crawl_starter: CrawlStarter,
    outbox_repository: OutboxRepository,
) -> None:
    await crawl_starter(
        StartCrawl(
            archive_id="archive-1",
            seed_url="https://example.org/",
            max_depth=1,
            max_pages=10,
        )
    )

    message = await outbox_repository.claim(60.0)

    assert message is not None

    with pytest.raises(InvalidRescheduleDelay):
        await outbox_repository.reschedule(message, -1.0)
