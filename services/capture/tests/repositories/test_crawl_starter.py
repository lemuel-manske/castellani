import json
from uuid import NAMESPACE_URL, uuid5

import pytest

from contracts.messages import CAPTURE_PAGE_EVENT
from domain.capture import (
    ArchivePage,
    InvalidURLIdentity,
    OutboxMessage,
    PageTask,
    StartCrawl,
    TaskClaim,
    identify_url,
)
from ports.capture import (
    ArchiveRetrieval,
    CrawlStarter,
    OutboxRepository,
    TaskRepository,
)

pytestmark = pytest.mark.integration


async def test_start_seeds_a_claimable_seed_page(
    crawl_starter: CrawlStarter,
    task_repository: TaskRepository,
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

    claim = await task_repository.claim("archive-1", identity.url_key)

    assert claim == TaskClaim(
        task=PageTask(
            archive_id="archive-1",
            url_key=identity.url_key,
            url=identity.navigation_url,
            depth=0,
        ),
        attempt_id="attempt-1",
        fence=1,
        lease_until=1_800_000_060.0,
    )


async def test_start_seeds_a_capture_page_outbox_message(
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


async def test_duplicate_start_does_not_create_another_message(
    crawl_starter: CrawlStarter,
    outbox_repository: OutboxRepository,
) -> None:
    started = StartCrawl(
        archive_id="archive-1",
        seed_url="https://example.org/",
        max_depth=1,
        max_pages=10,
    )

    await crawl_starter(started)
    await crawl_starter(started)

    message = await outbox_repository.claim(60.0)

    assert message is not None

    await outbox_repository.confirm(message)

    assert await outbox_repository.claim(60.0) is None


async def test_start_lists_the_seed_page_as_pending(
    crawl_starter: CrawlStarter,
    archive_retrieval: ArchiveRetrieval,
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

    listing = await archive_retrieval.list_pages("archive-1", limit=10, cursor=None)

    assert listing.items == (ArchivePage(url=identity.navigation_url, status="PENDING"),)


async def test_start_rejects_an_invalid_seed_url(
    crawl_starter: CrawlStarter,
) -> None:
    with pytest.raises(InvalidURLIdentity):
        await crawl_starter(
            StartCrawl(
                archive_id="archive-1",
                seed_url="not-a-url",
                max_depth=1,
                max_pages=10,
            )
        )
