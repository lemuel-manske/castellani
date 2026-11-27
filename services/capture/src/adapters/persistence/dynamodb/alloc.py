from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

from domain.capture import (
    CaptureReservation,
    CaptureReservationLostError,
    InvalidAttemptId,
    InvalidLeaseDuration,
    InvalidReservationRenewal,
    InvalidSlotCount,
    new_reservation_id,
)
from ports.capture import CaptureAllocator
from ports.clock import Clock

from .error_handling import raise_unless_conditional_failure
from .queries.alloc import (
    read_slot,
    release_slot,
    renew_slot,
    reservation_from_item,
    reserve_slot,
)
from .values import number_from_item, optional_string

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient

DEFAULT_SLOT_COUNT = 10
DEFAULT_LEASE_DURATION = 60


class DynamoDBCaptureAllocator(CaptureAllocator):
    """Coordinates fenced browser-capacity reservations through DynamoDB slot rows."""

    def __init__(
        self,
        client: DynamoDBClient,
        slot_count: int = DEFAULT_SLOT_COUNT,
        lease_duration: float = DEFAULT_LEASE_DURATION,
        clock: Clock = time.time,
    ) -> None:
        if slot_count < 1:
            raise InvalidSlotCount("slot_count must be positive")

        if lease_duration <= 0:
            raise InvalidLeaseDuration("lease_duration must be positive")

        self.client = client

        self.clock = clock

        self.slot_count = slot_count

        self.lease_duration = lease_duration

    async def reserve(self, attempt_id: str) -> CaptureReservation | None:
        if not attempt_id:
            raise InvalidAttemptId("attempt_id must not be empty")

        reservation_id = new_reservation_id(attempt_id)

        def find_existing_reservation() -> CaptureReservation | None:
            for slot_number in range(self.slot_count):
                slot_id = str(slot_number)

                item = read_slot(self.client, slot_id)

                if (
                    item is not None
                    and optional_string(item, "ownerAttemptId") == attempt_id
                    and optional_string(item, "reservationId") == reservation_id
                    and number_from_item(item, "leaseUntil", "browser slot") > self.clock()
                ):
                    return reservation_from_item(slot_id, item)

            return None

        def reserve() -> CaptureReservation | None:
            existing = find_existing_reservation()

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
                    raise_unless_conditional_failure(error)

                    existing = read_slot(self.client, slot_id)

                    if (
                        existing is not None
                        and optional_string(existing, "ownerAttemptId") == attempt_id
                        and optional_string(existing, "reservationId") == reservation_id
                        and number_from_item(existing, "leaseUntil", "browser slot") > self.clock()
                    ):
                        return reservation_from_item(slot_id, existing)

                    continue

                return reservation_from_item(slot_id, response["Attributes"])

            return None

        return await asyncio.to_thread(reserve)

    async def renew(self, reservation: CaptureReservation) -> CaptureReservation:
        def renew() -> CaptureReservation:
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
                raise_unless_conditional_failure(error)

                raise CaptureReservationLostError(
                    "browser capacity reservation is no longer owned"
                ) from error

            renewed = reservation_from_item(reservation.slot_id, response["Attributes"])

            try:
                reservation.verify_renewal(renewed, now)
            except InvalidReservationRenewal as error:
                raise CaptureReservationLostError(
                    "browser capacity reservation renewal returned an invalid reservation"
                ) from error

            return renewed

        return await asyncio.to_thread(renew)

    async def release(self, reservation: CaptureReservation) -> None:
        def release() -> None:
            try:
                release_slot(
                    self.client,
                    reservation.slot_id,
                    reservation.attempt_id,
                    reservation.reservation_id,
                    reservation.fence,
                )
            except ClientError as error:
                raise_unless_conditional_failure(error)

        await asyncio.to_thread(release)
