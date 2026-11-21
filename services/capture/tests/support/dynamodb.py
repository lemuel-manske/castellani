import threading
from copy import deepcopy
from typing import Any, NoReturn

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


class FakeDynamoDBFrontierClient:
    """Applies run guards, frontier transitions, and outbox writes atomically."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.frontier: dict[tuple[str, str], dict[str, Any]] = {}
        self.outbox: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

    def transact_write_items(self, **request: Any) -> dict[str, Any]:
        operations = request["TransactItems"]
        run_check = next(
            operation["ConditionCheck"] for operation in operations if "ConditionCheck" in operation
        )
        frontier_update = next(
            operation["Update"] for operation in operations if "Update" in operation
        )
        outbox_put = next(
            (operation["Put"] for operation in operations if "Put" in operation),
            None,
        )

        with self.lock:
            run_key = run_check["Key"]["archiveId"]["S"]
            run = self.runs.get(run_key)
            run_admission = run.get("admission", {}).get("S") if run else None

            update_key = frontier_update["Key"]
            key = (
                update_key["archiveId"]["S"],
                update_key["urlKey"]["S"],
            )
            item = deepcopy(self.frontier.get(key))
            names = frontier_update["ExpressionAttributeNames"]
            values = frontier_update["ExpressionAttributeValues"]
            condition = frontier_update["ConditionExpression"]

            if run_admission != run_check["ExpressionAttributeValues"][":open"]["S"]:
                reasons = ["None"] * len(operations)
                reasons[0] = "ConditionalCheckFailed"
                self._transaction_failure(*reasons)

            if item is None:
                reasons = ["None"] * len(operations)
                reasons[1] = "ConditionalCheckFailed"
                self._transaction_failure(*reasons)

            updated = deepcopy(item)

            if "#state = :pending" in condition:
                is_pending = updated.get(names["#state"]) == values[":pending"]
                is_expired = updated.get(names["#state"]) == values[":claimed"] and float(
                    updated[names["#lease"]]["N"]
                ) <= float(values[":now"]["N"])

                if not is_pending and not is_expired:
                    reasons = ["None"] * len(operations)
                    reasons[1] = "ConditionalCheckFailed"
                    self._transaction_failure(*reasons)

                fence = int(updated.get(names["#fence"], {"N": "0"})["N"]) + 1
                updated[names["#state"]] = deepcopy(values[":claimed"])
                updated[names["#attempt"]] = deepcopy(values[":attempt"])
                updated[names["#lease"]] = deepcopy(values[":lease"])
                updated[names["#fence"]] = {"N": str(fence)}
            elif "REMOVE #attempt" in frontier_update["UpdateExpression"]:
                owns_claim = (
                    updated.get(names["#state"]) == values[":claimed"]
                    and updated.get(names["#attempt"]) == values[":attempt"]
                    and updated.get(names["#fence"]) == values[":fence"]
                    and float(updated[names["#lease"]]["N"]) > float(values[":now"]["N"])
                )

                if not owns_claim:
                    reasons = ["None"] * len(operations)
                    reasons[1] = "ConditionalCheckFailed"
                    self._transaction_failure(*reasons)

                updated[names["#state"]] = deepcopy(values[":pending"])
                updated.pop(names["#attempt"], None)
                updated.pop(names["#lease"], None)
            else:
                owns_claim = (
                    updated.get(names["#state"]) == values[":claimed"]
                    and updated.get(names["#attempt"]) == values[":attempt"]
                    and updated.get(names["#fence"]) == values[":fence"]
                    and float(updated[names["#lease"]]["N"]) > float(values[":now"]["N"])
                )

                if not owns_claim:
                    reasons = ["None"] * len(operations)
                    reasons[1] = "ConditionalCheckFailed"
                    self._transaction_failure(*reasons)

                updated[names["#lease"]] = deepcopy(values[":lease"])

            if outbox_put is None:
                self.frontier[key] = updated
                return {}

            outbox_item = outbox_put["Item"]
            message_id = outbox_item["messageId"]["S"]

            if message_id in self.outbox:
                reasons = ["None"] * len(operations)
                reasons[2] = "ConditionalCheckFailed"
                self._transaction_failure(*reasons)

            self.frontier[key] = updated
            self.outbox[message_id] = deepcopy(outbox_item)

            return {}

    def get_item(self, **request: Any) -> dict[str, Any]:
        key = request["Key"]

        with self.lock:
            table_name = request["TableName"]

            if table_name == "capture_runs":
                item = self.runs.get(key["archiveId"]["S"])
            elif table_name == "capture_outbox":
                item = self.outbox.get(key["messageId"]["S"])
            else:
                item = self.frontier.get((key["archiveId"]["S"], key["urlKey"]["S"]))

            return {"Item": deepcopy(item)} if item else {}

    @staticmethod
    def _transaction_failure(*reasons: str) -> NoReturn:
        raise ClientError(
            {
                "Error": {
                    "Code": "TransactionCanceledException",
                    "Message": "The transaction was cancelled.",
                },
                "CancellationReasons": [{"Code": reason} for reason in reasons],
            },
            "TransactWriteItems",
        )


class FakeDynamoDBOutboxClient:
    """Thread-safe DynamoDB subset for exercising outbox delivery transitions."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

    def query(self, **request: Any) -> dict[str, Any]:
        status = request["ExpressionAttributeValues"][":status"]["S"]
        now = float(request["ExpressionAttributeValues"][":now"]["N"])

        with self.lock:
            items = [
                deepcopy(item)
                for item in self.items.values()
                if item["status"]["S"] == status
                and float(item["nextAttemptAt"]["N"]) <= now
            ]

        items.sort(key=lambda item: float(item["nextAttemptAt"]["N"]))

        return {"Items": items[: request["Limit"]]}

    def update_item(self, **request: Any) -> dict[str, Any]:
        message_id = request["Key"]["messageId"]["S"]
        names = request.get("ExpressionAttributeNames", {})
        values = request.get("ExpressionAttributeValues", {})

        with self.lock:
            item = self.items.get(message_id)

            if item is None:
                self._conditional_failure()

            condition = request["ConditionExpression"]

            if "#next_attempt = :due_at" in condition:
                matches = (
                    item.get(names["#status"]) == values[":status"]
                    and item.get(names["#next_attempt"]) == values[":due_at"]
                )
            else:
                matches = (
                    item.get(names["#status"]) == values[":claimed"]
                    and item.get(names["#lease_token"]) == values[":lease_token"]
                )

                if "#next_attempt > :lease_now" in condition:
                    matches = matches and float(item[names["#next_attempt"]]["N"]) > float(
                        values[":lease_now"]["N"]
                    )
                elif "#next_attempt > :now" in condition:
                    matches = matches and float(item[names["#next_attempt"]]["N"]) > float(
                        values[":now"]["N"]
                    )

            if not matches:
                self._conditional_failure()

            updated = deepcopy(item)
            expression = request["UpdateExpression"]

            if "ADD #attempts :one" in expression:
                updated[names["#status"]] = deepcopy(values[":claimed"])
                updated[names["#lease_token"]] = deepcopy(values[":lease_token"])
                updated[names["#next_attempt"]] = deepcopy(values[":lease_until"])
                attempts = int(updated.get(names["#attempts"], {"N": "0"})["N"]) + 1
                updated[names["#attempts"]] = {"N": str(attempts)}
            elif "REMOVE #lease_token" in expression and "#published_at" in names:
                updated[names["#status"]] = deepcopy(values[":published"])
                updated[names["#published_at"]] = deepcopy(values[":now"])
                updated.pop(names["#lease_token"], None)
            else:
                updated[names["#status"]] = deepcopy(values[":pending"])
                updated[names["#next_attempt"]] = deepcopy(values[":next_attempt"])
                updated.pop(names["#lease_token"], None)

            self.items[message_id] = updated

            if request.get("ReturnValues") == "ALL_NEW":
                return {"Attributes": deepcopy(updated)}

            return {}

    @staticmethod
    def _conditional_failure() -> NoReturn:
        raise ClientError(
            {
                "Error": {
                    "Code": "ConditionalCheckFailedException",
                    "Message": "The conditional request was not satisfied.",
                }
            },
            "UpdateItem",
        )
