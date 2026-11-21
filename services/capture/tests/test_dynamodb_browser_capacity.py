import asyncio
from typing import Any

import pytest
from support.dynamodb import FakeClock

from adapters.persistence.dynamodb.browser_capacity import (
    BrowserReservationLostError,
    DynamoDBBrowserCapacity,
)


async def test_capacity_admits_exactly_the_configured_number_of_contenders(dynamodb_client: Any) -> None:
    client = dynamodb_client

    capacity = DynamoDBBrowserCapacity(
        client=client,
        table_name="capture_browser_slots",
        slot_count=10,
        lease_duration=30,
    )

    reservations = await asyncio.gather(
        *(capacity.reserve(f"attempt-{number}") for number in range(100))
    )

    acquired = [reservation for reservation in reservations if reservation is not None]

    assert len(acquired) == 10
    assert len({reservation.slot_id for reservation in acquired}) == 10
    assert len({reservation.reservation_id for reservation in acquired}) == 10


async def test_reservation_renewal_preserves_its_fence(
    dynamodb_client: Any,
) -> None:
    clock = FakeClock()
    client = dynamodb_client

    capacity = DynamoDBBrowserCapacity(
        client=client,
        table_name="capture_browser_slots",
        slot_count=1,
        lease_duration=30,
        clock=clock,
    )

    reservation = await capacity.reserve("attempt-1")
    assert reservation is not None

    clock.advance(10)
    renewed = await capacity.renew(reservation)

    assert renewed.slot_id == reservation.slot_id
    assert renewed.attempt_id == reservation.attempt_id
    assert renewed.reservation_id == reservation.reservation_id
    assert renewed.fence == reservation.fence
    assert renewed.lease_until > reservation.lease_until


async def test_expired_reservation_is_reclaimed_with_a_new_fence(dynamodb_client: Any) -> None:
    clock = FakeClock()
    client = dynamodb_client

    capacity = DynamoDBBrowserCapacity(
        client=client,
        table_name="capture_browser_slots",
        slot_count=1,
        lease_duration=30,
        clock=clock,
    )

    previous = await capacity.reserve("attempt-1")
    assert previous is not None

    clock.advance(31)

    current = await capacity.reserve("attempt-2")
    assert current is not None

    assert current.attempt_id == "attempt-2"
    assert current.slot_id == previous.slot_id
    assert current.fence == previous.fence + 1

    with pytest.raises(BrowserReservationLostError):
        await capacity.renew(previous)

    await capacity.release(previous)
    assert await capacity.reserve("attempt-3") is None


async def test_release_is_idempotent_and_stale_release_cannot_free_new_owner(
    dynamodb_client: Any,
) -> None:
    clock = FakeClock()
    client = dynamodb_client

    capacity = DynamoDBBrowserCapacity(
        client=client,
        table_name="capture_browser_slots",
        slot_count=1,
        lease_duration=30,
        clock=clock,
    )

    previous = await capacity.reserve("attempt-1")
    assert previous is not None

    await capacity.release(previous)
    await capacity.release(previous)

    current = await capacity.reserve("attempt-2")
    assert current is not None

    assert current.fence == previous.fence + 1

    await capacity.release(previous)
    assert await capacity.reserve("attempt-3") is None


def test_capacity_rejects_invalid_configuration(dynamodb_client: Any) -> None:
    client = dynamodb_client

    with pytest.raises(ValueError):
        DynamoDBBrowserCapacity(client, "capture_browser_slots", 0, 30)

    with pytest.raises(ValueError):
        DynamoDBBrowserCapacity(client, "capture_browser_slots", 1, 0)


async def test_repeated_reservation_reuses_existing_slot(
    dynamodb_client: Any,
) -> None:
    client = dynamodb_client

    capacity = DynamoDBBrowserCapacity(
        client=client,
        table_name="capture_browser_slots",
        slot_count=2,
        lease_duration=30,
    )

    first = await capacity.reserve("attempt-1")
    second = await capacity.reserve("attempt-2")

    assert first is not None
    assert second is not None

    assert first.slot_id == "0"
    assert second.slot_id == "1"

    await capacity.release(first)
    retried = await capacity.reserve("attempt-2")

    assert retried == second
