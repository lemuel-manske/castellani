import asyncio
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

from application import DuplicateSessionRequest, SessionConflict
from domain import AuthSession, SessionStatus, SessionStore

from .queries.task import read_run
from .tables import RUNS_TABLE, SESSION_REQUESTS_TABLE, SESSIONS_TABLE

ACTIVE_SESSION_STATUSES = frozenset(
    {
        SessionStatus.CREATED,
        SessionStatus.ACTIVE,
        SessionStatus.FINALIZING,
    }
)

GENERATION_ATTEMPTS = 5


class DynamoDBSessionStore(SessionStore):
    def __init__(
        self,
        client: Any,
        session_ttl_seconds: int,
        auth_profile_bucket: str,
    ) -> None:
        self.client = client
        self.session_ttl_seconds = session_ttl_seconds
        self.auth_profile_bucket = auth_profile_bucket

    async def create(self, session: AuthSession, key: str, fingerprint: str) -> None:
        now = datetime.now(UTC)
        now_epoch = int(now.timestamp())
        expires_at = now.timestamp() + self.session_ttl_seconds

        def put() -> None:
            try:
                self.client.transact_write_items(
                    TransactItems=[
                        {
                            "Put": {
                                "TableName": SESSIONS_TABLE,
                                "Item": session_item(session, expires_at),
                                "ConditionExpression": "attribute_not_exists(sessionId)",
                            }
                        },
                        {
                            "Put": {
                                "TableName": SESSION_REQUESTS_TABLE,
                                "Item": {
                                    "idempotencyKey": {"S": key},
                                    "sessionId": {"S": session.session_id},
                                    "fingerprint": {"S": fingerprint},
                                    "expiresAtEpoch": {"N": str(int(expires_at))},
                                },
                                "ConditionExpression": (
                                    "attribute_not_exists(idempotencyKey) OR expiresAtEpoch <= :now"
                                ),
                                "ExpressionAttributeValues": {":now": {"N": str(now_epoch)}},
                            }
                        },
                    ]
                )
            except ClientError as error:
                if conditional_check_failed(error):
                    raise DuplicateSessionRequest from error

                raise

        await asyncio.to_thread(put)

    async def get(self, session_id: str) -> AuthSession | None:
        def read() -> dict[str, Any] | None:
            response = self.client.get_item(
                TableName=SESSIONS_TABLE,
                Key={"sessionId": {"S": session_id}},
                ConsistentRead=True,
            )

            return response.get("Item")

        item = await asyncio.to_thread(read)

        return session_from_item(item) if item else None

    async def find_by_request(self, key: str, fingerprint: str) -> str | None:
        def read() -> dict[str, Any] | None:
            response = self.client.get_item(
                TableName=SESSION_REQUESTS_TABLE,
                Key={"idempotencyKey": {"S": key}},
                ConsistentRead=True,
            )

            return response.get("Item")

        item = await asyncio.to_thread(read)

        if not item:
            return None

        if int(item["expiresAtEpoch"]["N"]) <= datetime.now(UTC).timestamp():
            return None

        if item["fingerprint"]["S"] != fingerprint:
            raise SessionConflict("idempotency key was reused with a different body")

        return item["sessionId"]["S"]

    async def save(self, session: AuthSession) -> None:
        names = {"#status": "status", "#version": "version", "#updated": "updatedAt"}
        values: dict[str, Any] = {
            ":status": {"S": str(session.status)},
            ":version": {"N": str(session.version)},
            ":expected": {"N": str(session.version - 1)},
            ":updated": {"S": utc_now()},
        }
        expression = "SET #status = :status, #version = :version, #updated = :updated"

        if session.auth_generation is not None:
            names["#generation"] = "authGeneration"
            values[":generation"] = {"N": str(session.auth_generation)}
            expression += ", #generation = :generation"

        if session.profile_key is not None:
            names["#profile"] = "profileKey"
            values[":profile"] = {"S": session.profile_key}
            expression += ", #profile = :profile"

        if session.vnc_origin is not None:
            names["#origin"] = "vncOrigin"
            values[":origin"] = {"S": session.vnc_origin}
            expression += ", #origin = :origin"

        if session.failure_reason is not None:
            names["#reason"] = "failureReason"
            values[":reason"] = {"S": session.failure_reason}
            expression += ", #reason = :reason"

        def update() -> None:
            try:
                self.client.update_item(
                    TableName=SESSIONS_TABLE,
                    Key={"sessionId": {"S": session.session_id}},
                    UpdateExpression=expression,
                    ConditionExpression="#version = :expected",
                    ExpressionAttributeNames=names,
                    ExpressionAttributeValues=values,
                )
            except ClientError as error:
                if conditional_check_failed(error):
                    raise SessionConflict from error

                raise

        await asyncio.to_thread(update)

    async def reserve_generation(self, archive_id: str) -> int:
        def reserve() -> int:
            for _ in range(GENERATION_ATTEMPTS):
                run = read_run(self.client, RUNS_TABLE, archive_id)

                if run is None:
                    raise SessionConflict("archive run does not exist")

                current = int(run.get("authGeneration", {}).get("N", "0"))
                generation = current + 1

                try:
                    self.client.update_item(
                        TableName=RUNS_TABLE,
                        Key={"archiveId": {"S": archive_id}},
                        UpdateExpression=(
                            "SET authGeneration = :generation, authUpdatedAt = :updated"
                        ),
                        ConditionExpression=(
                            "attribute_not_exists(authGeneration) OR authGeneration = :current"
                        ),
                        ExpressionAttributeValues={
                            ":generation": {"N": str(generation)},
                            ":current": {"N": str(current)},
                            ":updated": {"S": utc_now()},
                        },
                    )
                except ClientError as error:
                    if conditional_check_failed(error):
                        continue

                    raise

                return generation

            raise SessionConflict("authentication generation changed concurrently")

        return await asyncio.to_thread(reserve)

    async def set_profile(self, archive_id: str, generation: int, key: str) -> None:
        def update() -> None:
            self.client.update_item(
                TableName=RUNS_TABLE,
                Key={"archiveId": {"S": archive_id}},
                UpdateExpression=(
                    "SET authProfileKey = :key, authProfileBucket = :bucket, "
                    "authUpdatedAt = :updated"
                ),
                ConditionExpression="authGeneration = :generation",
                ExpressionAttributeValues={
                    ":key": {"S": key},
                    ":bucket": {"S": self.auth_profile_bucket},
                    ":generation": {"N": str(generation)},
                    ":updated": {"S": utc_now()},
                },
            )

        await asyncio.to_thread(update)

    async def reconcile_abandoned(self, manager_id: str) -> None:
        def reconcile() -> None:
            cursor: dict[str, Any] | None = None

            while True:
                scan_args: dict[str, Any] = {"TableName": SESSIONS_TABLE}

                if cursor:
                    scan_args["ExclusiveStartKey"] = cursor

                response = self.client.scan(**scan_args)

                for item in response.get("Items", []):
                    status = SessionStatus(item["status"]["S"])

                    if status not in ACTIVE_SESSION_STATUSES:
                        continue

                    session = session_from_item(item)
                    reason = None

                    if session.manager_id != manager_id:
                        reason = "login manager restarted"
                    elif session.expired():
                        reason = "session expired"

                    if reason is None:
                        continue

                    new_status = (
                        SessionStatus.EXPIRED
                        if reason == "session expired"
                        else SessionStatus.FAILED
                    )

                    try:
                        self.client.update_item(
                            TableName=SESSIONS_TABLE,
                            Key={"sessionId": {"S": session.session_id}},
                            UpdateExpression=(
                                "SET #status = :status, #version = :version, "
                                "#reason = :reason, #updated = :updated"
                            ),
                            ConditionExpression="#version = :expected",
                            ExpressionAttributeNames={
                                "#status": "status",
                                "#version": "version",
                                "#reason": "failureReason",
                                "#updated": "updatedAt",
                            },
                            ExpressionAttributeValues={
                                ":status": {"S": str(new_status)},
                                ":version": {"N": str(session.version + 1)},
                                ":expected": {"N": str(session.version)},
                                ":reason": {"S": reason},
                                ":updated": {"S": utc_now()},
                            },
                        )
                    except ClientError as error:
                        if not conditional_check_failed(error):
                            raise

                cursor = response.get("LastEvaluatedKey")

                if not cursor:
                    return

        await asyncio.to_thread(reconcile)


def session_item(session: AuthSession, expires_at: float) -> dict[str, Any]:
    now = utc_now()
    item: dict[str, Any] = {
        "sessionId": {"S": session.session_id},
        "archiveId": {"S": session.archive_id},
        "targetUrl": {"S": session.target_url},
        "status": {"S": str(session.status)},
        "expiresAt": {"S": session.expires_at},
        "expiresAtEpoch": {"N": str(int(expires_at))},
        "managerId": {"S": session.manager_id},
        "version": {"N": str(session.version)},
        "createdAt": {"S": now},
        "updatedAt": {"S": now},
    }

    if session.auth_generation is not None:
        item["authGeneration"] = {"N": str(session.auth_generation)}

    if session.profile_key is not None:
        item["profileKey"] = {"S": session.profile_key}

    if session.vnc_origin is not None:
        item["vncOrigin"] = {"S": session.vnc_origin}

    return item


def session_from_item(item: dict[str, Any]) -> AuthSession:
    return AuthSession(
        session_id=item["sessionId"]["S"],
        archive_id=item["archiveId"]["S"],
        target_url=item["targetUrl"]["S"],
        status=SessionStatus(item["status"]["S"]),
        expires_at=item["expiresAt"]["S"],
        manager_id=item["managerId"]["S"],
        version=int(item["version"]["N"]),
        auth_generation=optional_number(item, "authGeneration"),
        profile_key=optional_string(item, "profileKey"),
        vnc_origin=optional_string(item, "vncOrigin"),
        failure_reason=optional_string(item, "failureReason"),
    )


def optional_number(item: dict[str, Any], name: str) -> int | None:
    value = item.get(name)

    return int(value["N"]) if value else None


def optional_string(item: dict[str, Any], name: str) -> str | None:
    value = item.get(name)

    return value["S"] if value else None


def conditional_check_failed(error: ClientError) -> bool:
    details = error.response.get("Error", {})

    return details.get("Code") == "ConditionalCheckFailedException"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
