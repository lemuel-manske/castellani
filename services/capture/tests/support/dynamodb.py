import threading
from copy import deepcopy
from typing import Any

from botocore.exceptions import ClientError


class FakeClock:
    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeDynamoDBClient:
    """Thread-safe DynamoDB subset for exercising conditional browser-slot updates."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

    def update_item(self, **request: Any) -> dict[str, Any]:
        slot_id = request["Key"]["slotId"]["S"]

        with self.lock:
            item = deepcopy(self.items.get(slot_id, {"slotId": {"S": slot_id}}))
            names = request.get("ExpressionAttributeNames", {})
            values = request.get("ExpressionAttributeValues", {})
            condition = request["ConditionExpression"]

            if "attribute_not_exists" in condition:
                owner_name = names["#owner"]
                lease_name = names["#lease"]
                owner = item.get(owner_name)
                expired = owner is not None and float(item[lease_name]["N"]) <= float(
                    values[":now"]["N"]
                )

                if owner is not None and not expired:
                    self._conditional_failure("UpdateItem")

                fence = int(item.get(names["#fence"], {"N": "0"})["N"]) + 1
                item[owner_name] = deepcopy(values[":attempt"])
                item[names["#reservation"]] = deepcopy(values[":reservation"])
                item[lease_name] = deepcopy(values[":lease"])
                item[names["#fence"]] = {"N": str(fence)}
            elif "REMOVE" in request["UpdateExpression"]:
                if not self._owns(item, names, values):
                    self._conditional_failure("UpdateItem")

                for name in ("#owner", "#reservation", "#lease"):
                    item.pop(names[name], None)
            else:
                if not self._owns(item, names, values):
                    self._conditional_failure("UpdateItem")

                if float(item[names["#lease"]]["N"]) <= float(values[":now"]["N"]):
                    self._conditional_failure("UpdateItem")

                item[names["#lease"]] = deepcopy(values[":lease"])

            self.items[slot_id] = item

            if request.get("ReturnValues") == "ALL_NEW":
                return {"Attributes": deepcopy(item)}

            return {}

    def get_item(self, **request: Any) -> dict[str, Any]:
        slot_id = request["Key"]["slotId"]["S"]

        with self.lock:
            item = self.items.get(slot_id)
            return {"Item": deepcopy(item)} if item else {}

    @staticmethod
    def _owns(
        item: dict[str, Any],
        names: dict[str, str],
        values: dict[str, Any],
    ) -> bool:
        return (
            item.get(names["#owner"]) == values[":attempt"]
            and item.get(names["#reservation"]) == values[":reservation"]
            and item.get(names["#fence"]) == values[":fence"]
        )

    @staticmethod
    def _conditional_failure(operation: str) -> None:
        raise ClientError(
            {
                "Error": {
                    "Code": "ConditionalCheckFailedException",
                    "Message": "The conditional request was not satisfied.",
                }
            },
            operation,
        )
