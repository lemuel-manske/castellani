import asyncio
from collections.abc import Callable
from hashlib import sha256
import time
from typing import Any

from botocore.exceptions import ClientError

from application.contracts import BrowserReservation


class BrowserReservationLostError(RuntimeError):
    """Raised when a reservation can no longer be renewed by its owner."""


class DynamoDBBrowserCapacity:
    """Coordinates fenced browser-capacity reservations through DynamoDB slot rows."""

    def __init__(
        self,
        client: Any,
        table_name: str,
        slot_count: int,
        lease_duration: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not table_name:
            raise ValueError("table_name must not be empty")

        if slot_count < 1:
            raise ValueError("slot_count must be positive")

        if lease_duration <= 0:
            raise ValueError("lease_duration must be positive")

        self.client = client
        self.table_name = table_name
        self.slot_count = slot_count
        self.lease_duration = lease_duration
        self.clock = clock

    async def reserve(self, attempt_id: str) -> BrowserReservation | None:
        if not attempt_id:
            raise ValueError("attempt_id must not be empty")

        reservation_id = self._reservation_id(attempt_id)

        return await asyncio.to_thread(
            self._reserve,
            attempt_id,
            reservation_id,
        )

    async def renew(self, reservation: BrowserReservation) -> BrowserReservation:
        return await asyncio.to_thread(self._renew, reservation)

    async def release(self, reservation: BrowserReservation) -> None:
        await asyncio.to_thread(self._release, reservation)

    def _reserve(
        self,
        attempt_id: str,
        reservation_id: str,
    ) -> BrowserReservation | None:
        existing = self._find_existing_reservation(attempt_id, reservation_id)

        if existing is not None:
            return existing

        for slot_number in range(self.slot_count):
            slot_id = str(slot_number)
            now = self.clock()
            lease_until = now + self.lease_duration

            try:
                response = self.client.update_item(
                    TableName=self.table_name,
                    Key={"slotId": {"S": slot_id}},
                    UpdateExpression=(
                        "SET #owner = :attempt, #reservation = :reservation, "
                        "#lease = :lease, #fence = if_not_exists(#fence, :zero) + :one"
                    ),
                    ConditionExpression=(
                        "attribute_not_exists(#owner) OR #lease <= :now"
                    ),
                    ExpressionAttributeNames={
                        "#owner": "ownerAttemptId",
                        "#reservation": "reservationId",
                        "#lease": "leaseUntil",
                        "#fence": "fence",
                    },
                    ExpressionAttributeValues={
                        ":attempt": {"S": attempt_id},
                        ":reservation": {"S": reservation_id},
                        ":lease": {"N": str(lease_until)},
                        ":now": {"N": str(now)},
                        ":zero": {"N": "0"},
                        ":one": {"N": "1"},
                    },
                    ReturnValues="ALL_NEW",
                )
            except ClientError as error:
                if not self._is_conditional_failure(error):
                    raise

                existing = self._read_slot(slot_id)
                if (
                    existing is not None
                    and existing.get("ownerAttemptId", {}).get("S") == attempt_id
                    and existing.get("reservationId", {}).get("S") == reservation_id
                    and self._number(existing, "leaseUntil") > self.clock()
                ):
                    return self._reservation_from_item(slot_id, existing)

                continue

            return self._reservation_from_item(slot_id, response["Attributes"])

        return None

    def _renew(self, reservation: BrowserReservation) -> BrowserReservation:
        now = self.clock()
        lease_until = now + self.lease_duration

        try:
            response = self.client.update_item(
                TableName=self.table_name,
                Key={"slotId": {"S": reservation.slot_id}},
                UpdateExpression="SET #lease = :lease",
                ConditionExpression=(
                    "#owner = :attempt AND #reservation = :reservation "
                    "AND #fence = :fence AND #lease > :now"
                ),
                ExpressionAttributeNames={
                    "#owner": "ownerAttemptId",
                    "#reservation": "reservationId",
                    "#fence": "fence",
                    "#lease": "leaseUntil",
                },
                ExpressionAttributeValues={
                    ":attempt": {"S": reservation.attempt_id},
                    ":reservation": {"S": reservation.reservation_id},
                    ":fence": {"N": str(reservation.fence)},
                    ":lease": {"N": str(lease_until)},
                    ":now": {"N": str(now)},
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as error:
            if self._is_conditional_failure(error):
                raise BrowserReservationLostError(
                    "browser capacity reservation is no longer owned"
                ) from error

            raise

        renewed = self._reservation_from_item(reservation.slot_id, response["Attributes"])

        if renewed.lease_until <= max(reservation.lease_until, now):
            raise BrowserReservationLostError(
                "browser capacity renewal did not extend the lease"
            )

        return renewed

    def _release(self, reservation: BrowserReservation) -> None:
        try:
            self.client.update_item(
                TableName=self.table_name,
                Key={"slotId": {"S": reservation.slot_id}},
                UpdateExpression="REMOVE #owner, #reservation, #lease",
                ConditionExpression=(
                    "#owner = :attempt AND #reservation = :reservation AND #fence = :fence"
                ),
                ExpressionAttributeNames={
                    "#owner": "ownerAttemptId",
                    "#reservation": "reservationId",
                    "#lease": "leaseUntil",
                    "#fence": "fence",
                },
                ExpressionAttributeValues={
                    ":attempt": {"S": reservation.attempt_id},
                    ":reservation": {"S": reservation.reservation_id},
                    ":fence": {"N": str(reservation.fence)},
                },
            )
        except ClientError as error:
            if not self._is_conditional_failure(error):
                raise

    def _find_existing_reservation(
        self,
        attempt_id: str,
        reservation_id: str,
    ) -> BrowserReservation | None:
        for slot_number in range(self.slot_count):
            slot_id = str(slot_number)
            item = self._read_slot(slot_id)

            if (
                item is not None
                and item.get("ownerAttemptId", {}).get("S") == attempt_id
                and item.get("reservationId", {}).get("S") == reservation_id
                and self._number(item, "leaseUntil") > self.clock()
            ):
                return self._reservation_from_item(slot_id, item)

        return None

    def _read_slot(self, slot_id: str) -> dict[str, Any] | None:
        response = self.client.get_item(
            TableName=self.table_name,
            Key={"slotId": {"S": slot_id}},
            ConsistentRead=True,
        )

        item = response.get("Item")
        return item if item else None

    @staticmethod
    def _reservation_id(attempt_id: str) -> str:
        digest = sha256(attempt_id.encode("utf-8")).hexdigest()
        return f"browser-{digest}"

    @staticmethod
    def _number(item: dict[str, Any], name: str) -> float:
        try:
            return float(item[name]["N"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"DynamoDB browser slot has invalid {name}") from error

    @classmethod
    def _reservation_from_item(
        cls,
        slot_id: str,
        item: dict[str, Any],
    ) -> BrowserReservation:
        try:
            attempt_id = item["ownerAttemptId"]["S"]
            reservation_id = item["reservationId"]["S"]
            fence = int(cls._number(item, "fence"))
            lease_until = cls._number(item, "leaseUntil")
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("DynamoDB returned an invalid browser slot") from error

        return BrowserReservation(
            attempt_id=attempt_id,
            reservation_id=reservation_id,
            slot_id=slot_id,
            fence=fence,
            lease_until=lease_until,
        )

    @staticmethod
    def _is_conditional_failure(error: ClientError) -> bool:
        return error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"
