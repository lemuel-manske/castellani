import asyncio

import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.clock import FakeClock

from adapters.persistence.dynamodb.alloc import (
    CaptureReservationLostError,
    DynamoDBCaptureAllocator,
)


@pytest.mark.integration
async def test_capacity_limits_concurrent_reservations(dynamodb: DynamoDBClient) -> None:
    capacity = DynamoDBCaptureAllocator(
        client=dynamodb,
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


@pytest.mark.integration
async def test_reservation_renewal_preserves_its_fence(
    dynamodb: DynamoDBClient, clock: FakeClock
) -> None:
    capacity = DynamoDBCaptureAllocator(
        client=dynamodb,
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


@pytest.mark.integration
async def test_expired_reservation_is_reclaimed_with_a_new_fence(
    dynamodb: DynamoDBClient, clock: FakeClock
) -> None:
    capacity = DynamoDBCaptureAllocator(
        client=dynamodb,
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

    with pytest.raises(CaptureReservationLostError):
        await capacity.renew(previous)

    await capacity.release(previous)
    assert await capacity.reserve("attempt-3") is None


@pytest.mark.integration
async def test_release_is_idempotent_and_stale_release_cannot_free_new_owner(
    dynamodb: DynamoDBClient, clock: FakeClock
) -> None:
    capacity = DynamoDBCaptureAllocator(
        client=dynamodb,
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


@pytest.mark.integration
def test_capacity_rejects_invalid_configuration(dynamodb: DynamoDBClient, clock: FakeClock) -> None:
    with pytest.raises(ValueError):
        DynamoDBCaptureAllocator(dynamodb, 0, 30, clock)

    with pytest.raises(ValueError):
        DynamoDBCaptureAllocator(dynamodb, 1, 0, clock)


@pytest.mark.integration
async def test_repeated_reservation_reuses_existing_slot(
    dynamodb: DynamoDBClient,
) -> None:
    capacity = DynamoDBCaptureAllocator(
        client=dynamodb,
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
