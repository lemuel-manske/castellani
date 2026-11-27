import pytest
from support.clock import SimpleClock

from domain.capture import (
    CaptureReservation,
    CaptureReservationLostError,
    InvalidAttemptId,
    new_reservation_id,
)
from ports.capture import CaptureAllocator

pytestmark = pytest.mark.integration


async def test_reserve_returns_a_fenced_slot_reservation(
    capture_allocator: CaptureAllocator,
) -> None:
    reservation = await capture_allocator.reserve("attempt-1")

    assert reservation == CaptureReservation(
        attempt_id="attempt-1",
        reservation_id=new_reservation_id("attempt-1"),
        slot_id="0",
        fence=1,
        lease_until=1_800_000_060.0,
    )


async def test_reserve_is_idempotent_for_the_same_attempt(
    capture_allocator: CaptureAllocator,
) -> None:
    first = await capture_allocator.reserve("attempt-1")
    second = await capture_allocator.reserve("attempt-1")

    assert first is not None
    assert second == first


async def test_reserve_uses_a_different_slot_for_each_attempt(
    capture_allocator: CaptureAllocator,
) -> None:
    first = await capture_allocator.reserve("attempt-1")
    second = await capture_allocator.reserve("attempt-2")

    assert first is not None
    assert first.slot_id == "0"
    assert second is not None
    assert second.slot_id == "1"


async def test_reserve_returns_none_when_all_slots_are_taken(
    capture_allocator: CaptureAllocator,
) -> None:
    await capture_allocator.reserve("attempt-1")
    await capture_allocator.reserve("attempt-2")

    assert await capture_allocator.reserve("attempt-3") is None


async def test_renew_extends_the_lease_without_changing_the_fence(
    capture_allocator: CaptureAllocator,
    clock: SimpleClock,
) -> None:
    reservation = await capture_allocator.reserve("attempt-1")

    assert reservation is not None

    clock.advance(10.0)

    renewed = await capture_allocator.renew(reservation)

    assert renewed == CaptureReservation(
        attempt_id="attempt-1",
        reservation_id=new_reservation_id("attempt-1"),
        slot_id="0",
        fence=1,
        lease_until=1_800_000_070.0,
    )


async def test_release_makes_the_slot_available_to_another_attempt(
    capture_allocator: CaptureAllocator,
) -> None:
    reservation = await capture_allocator.reserve("attempt-1")

    assert reservation is not None

    await capture_allocator.release(reservation)

    next_reservation = await capture_allocator.reserve("attempt-2")

    assert next_reservation == CaptureReservation(
        attempt_id="attempt-2",
        reservation_id=new_reservation_id("attempt-2"),
        slot_id="0",
        fence=2,
        lease_until=1_800_000_060.0,
    )


async def test_renew_rejects_a_released_reservation(
    capture_allocator: CaptureAllocator,
) -> None:
    reservation = await capture_allocator.reserve("attempt-1")

    assert reservation is not None

    await capture_allocator.release(reservation)
    await capture_allocator.reserve("attempt-2")

    with pytest.raises(CaptureReservationLostError):
        await capture_allocator.renew(reservation)


async def test_reserve_rejects_an_empty_attempt_id(
    capture_allocator: CaptureAllocator,
) -> None:
    with pytest.raises(InvalidAttemptId):
        await capture_allocator.reserve("")
