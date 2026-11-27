from typing import Any

from domain.capture import CaptureReservation
from topology.tables import BROWSER_SLOTS_TABLE

from ..values import number_from_item
from .common import reservation_condition


def read_slot(client: Any, slot_id: str) -> dict[str, Any] | None:
    response = client.get_item(
        TableName=BROWSER_SLOTS_TABLE,
        Key={"slotId": {"S": slot_id}},
        ConsistentRead=True,
    )

    item = response.get("Item")

    return item if item else None


def reservation_from_item(slot_id: str, item: dict[str, Any]) -> CaptureReservation:
    try:
        attempt_id = item["ownerAttemptId"]["S"]
        reservation_id = item["reservationId"]["S"]
        fence = int(number_from_item(item, "fence", "browser slot"))
        lease_until = number_from_item(item, "leaseUntil", "browser slot")
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("DynamoDB returned an invalid browser slot") from error

    return CaptureReservation(
        attempt_id=attempt_id,
        reservation_id=reservation_id,
        slot_id=slot_id,
        fence=fence,
        lease_until=lease_until,
    )


def reserve_slot(
    client: Any,
    slot_id: str,
    attempt_id: str,
    reservation_id: str,
    lease_until: float,
    now: float,
) -> dict[str, Any]:
    return client.update_item(
        TableName=BROWSER_SLOTS_TABLE,
        Key={"slotId": {"S": slot_id}},
        UpdateExpression=(
            "SET #owner = :attempt, #reservation = :reservation, "
            "#lease = :lease, #fence = if_not_exists(#fence, :zero) + :one"
        ),
        ConditionExpression="attribute_not_exists(#owner) OR #lease <= :now",
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


def renew_slot(
    client: Any,
    slot_id: str,
    attempt_id: str,
    reservation_id: str,
    fence: int,
    lease_until: float,
    now: float,
) -> dict[str, Any]:
    condition, names, values = reservation_condition(
        attempt_id,
        reservation_id,
        fence,
        now,
        lease_until,
    )

    return client.update_item(
        TableName=BROWSER_SLOTS_TABLE,
        Key={"slotId": {"S": slot_id}},
        UpdateExpression="SET #lease = :lease",
        ConditionExpression=condition,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )


def release_slot(
    client: Any,
    slot_id: str,
    attempt_id: str,
    reservation_id: str,
    fence: int,
) -> None:
    condition, names, values = reservation_condition(attempt_id, reservation_id, fence)

    client.update_item(
        TableName=BROWSER_SLOTS_TABLE,
        Key={"slotId": {"S": slot_id}},
        UpdateExpression="REMOVE #owner, #reservation, #lease",
        ConditionExpression=condition,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
