import json

import pytest
from support.dynamodb import FakeClock, FakeDynamoDBOutboxClient

from adapters.persistence.dynamodb.outbox import (
    DynamoDBOutbox,
    OUTBOX_CLAIMED,
    OUTBOX_PUBLISHED,
    OUTBOX_PENDING,
    OutboxLeaseLostError,
)


def outbox_item(next_attempt_at: float, status: str = OUTBOX_PENDING) -> dict:
    return {
        "messageId": {"S": "message-1"},
        "correlationId": {"S": "archive-1"},
        "type": {"S": "CapturePage"},
        "version": {"N": "1"},
        "occurredAt": {"S": "2026-11-20T12:00:00Z"},
        "payload": {
            "M": {
                "archiveId": {"S": "archive-1"},
                "urlKey": {"S": "url-1"},
            }
        },
        "status": {"S": status},
        "attempts": {"N": "0"},
        "nextAttemptAt": {"N": str(next_attempt_at)},
    }


async def test_claim_returns_due_message_and_acquires_delivery_lease() -> None:
    clock = FakeClock()
    client = FakeDynamoDBOutboxClient()
    client.items["message-1"] = outbox_item(clock() - 1)

    outbox = DynamoDBOutbox(
        client=client,
        table_name="capture_outbox",
        clock=clock,
        lease_token_factory=lambda: "lease-1",
    )

    message = await outbox.claim(30)

    assert message is not None
    assert message.message_id == "message-1"
    assert message.lease_token == "lease-1"
    assert json.loads(message.envelope) == {
        "messageId": "message-1",
        "correlationId": "archive-1",
        "type": "CapturePage",
        "version": 1,
        "occurredAt": "2026-11-20T12:00:00Z",
        "payload": {"archiveId": "archive-1", "urlKey": "url-1"},
    }

    item = client.items["message-1"]
    assert item["status"] == {"S": OUTBOX_CLAIMED}
    assert item["leaseToken"] == {"S": "lease-1"}
    assert item["nextAttemptAt"] == {"N": str(clock() + 30)}
    assert item["attempts"] == {"N": "1"}


async def test_claim_skips_messages_that_are_not_due() -> None:
    clock = FakeClock()
    client = FakeDynamoDBOutboxClient()
    client.items["message-1"] = outbox_item(clock() + 10)

    outbox = DynamoDBOutbox(
        client=client,
        table_name="capture_outbox",
        clock=clock,
    )

    assert await outbox.claim(30) is None
    assert client.items["message-1"]["status"] == {"S": OUTBOX_PENDING}


async def test_confirm_marks_the_message_delivered() -> None:
    clock = FakeClock()
    client = FakeDynamoDBOutboxClient()
    client.items["message-1"] = outbox_item(clock() - 1)
    outbox = DynamoDBOutbox(
        client=client,
        table_name="capture_outbox",
        clock=clock,
        lease_token_factory=lambda: "lease-1",
    )

    message = await outbox.claim(30)
    assert message is not None

    await outbox.confirm(message)

    item = client.items["message-1"]
    assert item["status"] == {"S": OUTBOX_PUBLISHED}
    assert item["publishedAt"] == {"S": "2027-01-15T08:00:00Z"}
    assert "leaseToken" not in item


async def test_reschedule_returns_message_to_pending_after_delay() -> None:
    clock = FakeClock()
    client = FakeDynamoDBOutboxClient()
    client.items["message-1"] = outbox_item(clock() - 1)
    tokens = iter(("lease-1", "lease-2"))
    outbox = DynamoDBOutbox(
        client=client,
        table_name="capture_outbox",
        clock=clock,
        lease_token_factory=lambda: next(tokens),
    )

    message = await outbox.claim(30)
    assert message is not None

    await outbox.reschedule(message, 15)

    item = client.items["message-1"]
    assert item["status"] == {"S": OUTBOX_PENDING}
    assert item["nextAttemptAt"] == {"N": str(clock() + 15)}
    assert "leaseToken" not in item
    assert item["attempts"] == {"N": "1"}

    assert await outbox.claim(30) is None

    clock.advance(15)
    retried = await outbox.claim(30)

    assert retried is not None
    assert retried.lease_token == "lease-2"
    assert client.items["message-1"]["attempts"] == {"N": "2"}


async def test_expired_claim_can_be_reclaimed_but_stale_lease_cannot_confirm() -> None:
    clock = FakeClock()
    client = FakeDynamoDBOutboxClient()
    client.items["message-1"] = outbox_item(clock() - 1)
    tokens = iter(("lease-1", "lease-2"))
    outbox = DynamoDBOutbox(
        client=client,
        table_name="capture_outbox",
        clock=clock,
        lease_token_factory=lambda: next(tokens),
    )

    first = await outbox.claim(10)
    assert first is not None

    clock.advance(11)
    second = await outbox.claim(10)
    assert second is not None
    assert second.lease_token == "lease-2"

    with pytest.raises(OutboxLeaseLostError):
        await outbox.confirm(first)

    await outbox.confirm(second)
    assert client.items["message-1"]["status"] == {"S": OUTBOX_PUBLISHED}


async def test_stale_lease_cannot_reschedule_a_reclaimed_message() -> None:
    clock = FakeClock()
    client = FakeDynamoDBOutboxClient()
    client.items["message-1"] = outbox_item(clock() - 1)
    tokens = iter(("lease-1", "lease-2"))
    outbox = DynamoDBOutbox(
        client=client,
        table_name="capture_outbox",
        clock=clock,
        lease_token_factory=lambda: next(tokens),
    )

    first = await outbox.claim(10)
    assert first is not None

    clock.advance(11)
    second = await outbox.claim(10)
    assert second is not None

    with pytest.raises(OutboxLeaseLostError):
        await outbox.reschedule(first, 5)

    assert client.items["message-1"]["leaseToken"] == {"S": "lease-2"}
