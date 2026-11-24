import asyncio
import time
from collections.abc import Callable
from typing import Any

from botocore.exceptions import ClientError

from domain.capture import CaptureAllocator, CaptureReservation, new_reservation_id

from .error_handling import is_conditional_failure
from .queries.alloc import (
    read_slot,
    release_slot,
    renew_slot,
    reservation_from_item,
    reserve_slot,
)
from .values import number_from_item

DEFAULT_SLOT_COUNT = 10
DEFAULT_LEASE_DURATION = 60


class CaptureReservationLostError(RuntimeError):
    """Raised when a reservation can no longer be renewed by its owner."""


class DynamoDBCaptureAllocator(CaptureAllocator):
    """Coordinates fenced browser-capacity reservations through DynamoDB slot rows."""

    def __init__(
        self,
        client: Any,
        slot_count: int = DEFAULT_SLOT_COUNT,
        lease_duration: float = DEFAULT_LEASE_DURATION,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if slot_count < 1:
            raise ValueError("slot_count must be positive")

        if lease_duration <= 0:
            raise ValueError("lease_duration must be positive")

        self.client = client

        self.clock = clock

        self.slot_count = slot_count

        self.lease_duration = lease_duration

    async def reserve(self, attempt_id: str) -> CaptureReservation | None:
        if not attempt_id:
            raise ValueError("attempt_id must not be empty")

        reservation_id = new_reservation_id(attempt_id)

        return await asyncio.to_thread(
            self._reserve,
            attempt_id,
            reservation_id,
        )

    async def renew(self, reservation: CaptureReservation) -> CaptureReservation:
        return await asyncio.to_thread(self._renew, reservation)

    async def release(self, reservation: CaptureReservation) -> None:
        await asyncio.to_thread(self._release, reservation)

    def _reserve(
        self,
        attempt_id: str,
        reservation_id: str,
    ) -> CaptureReservation | None:
        existing = self._find_existing_reservation(attempt_id, reservation_id)

        if existing is not None:
            return existing

        for slot_number in range(self.slot_count):
            slot_id = str(slot_number)

            now = self.clock()
            lease_until = now + self.lease_duration

            try:
                response = reserve_slot(
                    self.client,
                    slot_id,
                    attempt_id,
                    reservation_id,
                    lease_until,
                    now,
                )
            except ClientError as error:
                if not is_conditional_failure(error):
                    raise

                existing = read_slot(self.client, slot_id)

                if (
                    existing is not None
                    and existing.get("ownerAttemptId", {}).get("S") == attempt_id
                    and existing.get("reservationId", {}).get("S") == reservation_id
                    and number_from_item(existing, "leaseUntil", "browser slot") > self.clock()
                ):
                    return reservation_from_item(slot_id, existing)

                continue

            return reservation_from_item(slot_id, response["Attributes"])

        return None

    def _renew(self, reservation: CaptureReservation) -> CaptureReservation:
        now = self.clock()
        lease_until = now + self.lease_duration

        try:
            response = renew_slot(
                self.client,
                reservation.slot_id,
                reservation.attempt_id,
                reservation.reservation_id,
                reservation.fence,
                lease_until,
                now,
            )
        except ClientError as error:
            if is_conditional_failure(error):
                raise CaptureReservationLostError(
                    "browser capacity reservation is no longer owned"
                ) from error

            raise

        return reservation_from_item(reservation.slot_id, response["Attributes"])

    def _release(self, reservation: CaptureReservation) -> None:
        try:
            release_slot(
                self.client,
                reservation.slot_id,
                reservation.attempt_id,
                reservation.reservation_id,
                reservation.fence,
            )
        except ClientError as error:
            if not is_conditional_failure(error):
                raise

    def _find_existing_reservation(
        self,
        attempt_id: str,
        reservation_id: str,
    ) -> CaptureReservation | None:
        for slot_number in range(self.slot_count):
            slot_id = str(slot_number)

            item = read_slot(self.client, slot_id)

            if (
                item is not None
                and item.get("ownerAttemptId", {}).get("S") == attempt_id
                and item.get("reservationId", {}).get("S") == reservation_id
                and number_from_item(item, "leaseUntil", "browser slot") > self.clock()
            ):
                return reservation_from_item(slot_id, item)

        return None
