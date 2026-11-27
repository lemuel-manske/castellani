import asyncio
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

from domain.login import (
    ACTIVE_SESSION_STATUSES,
    AuthProfileReference,
    AuthSession,
    DuplicateSessionRequest,
    SessionConflict,
    SessionStatus,
)
from ports.login import SessionStore
from topology.buckets import AUTH_PROFILE_BUCKET
from utils.time import utc_now

from .error_handling import (
    raise_unless_canceled_or_conditional,
    raise_unless_conditional_failure,
)
from .queries.session import (
    create_session_transaction,
    fail_session,
    profile_reference_from_item,
    read_session,
    read_session_request,
    scan_sessions,
    session_from_item,
    update_generation,
    update_profile,
    update_session,
)
from .queries.task import read_run
from .values import number_from_item, string_from_item

GENERATION_ATTEMPTS = 5


class DynamoDBSessionStore(SessionStore):
    def __init__(self, client: Any, session_ttl_seconds: int | None = None) -> None:
        self.client = client
        self.session_ttl_seconds = session_ttl_seconds

    async def create(self, session: AuthSession, key: str, fingerprint: str) -> None:
        if self.session_ttl_seconds is None:
            raise RuntimeError("session TTL is required to create interactive sessions")

        now = datetime.now(UTC)

        now_epoch = int(now.timestamp())

        expires_at = now.timestamp() + self.session_ttl_seconds
        updated_at = utc_now()

        def put() -> None:
            try:
                create_session_transaction(
                    self.client,
                    session,
                    key,
                    fingerprint,
                    expires_at,
                    now_epoch,
                    updated_at,
                )
            except ClientError as error:
                raise_unless_canceled_or_conditional(error)

                raise DuplicateSessionRequest from error

        await asyncio.to_thread(put)

    async def get(self, session_id: str) -> AuthSession | None:
        item = await asyncio.to_thread(read_session, self.client, session_id)

        return session_from_item(item) if item else None

    async def find_by_request(self, key: str, fingerprint: str) -> str | None:
        item = await asyncio.to_thread(read_session_request, self.client, key)

        if not item:
            return None

        expires_at = number_from_item(item, "expiresAtEpoch", "session request")

        if expires_at <= datetime.now(UTC).timestamp():
            return None

        if string_from_item(item, "fingerprint", "session request") != fingerprint:
            raise SessionConflict("idempotency key was reused with a different body")

        return string_from_item(item, "sessionId", "session request")

    async def save(self, session: AuthSession) -> None:
        updated_at = utc_now()

        def update() -> None:
            try:
                update_session(self.client, session, updated_at)
            except ClientError as error:
                raise_unless_conditional_failure(error)

                raise SessionConflict from error

        await asyncio.to_thread(update)

    async def reserve_generation(self, archive_id: str) -> int:
        def reserve() -> int:
            for _ in range(GENERATION_ATTEMPTS):
                run = read_run(self.client, archive_id)

                if run is None:
                    raise SessionConflict("archive run does not exist")

                current = int(number_from_item(run, "authGeneration", "capture run", default=0))
                generation = current + 1

                try:
                    update_generation(
                        self.client,
                        archive_id,
                        generation,
                        current,
                        utc_now(),
                    )
                except ClientError as error:
                    raise_unless_conditional_failure(error)

                    continue

                return generation

            raise SessionConflict("authentication generation changed concurrently")

        return await asyncio.to_thread(reserve)

    async def set_profile(self, archive_id: str, generation: int, key: str) -> None:
        def update() -> None:
            update_profile(
                self.client,
                archive_id,
                generation,
                key,
                AUTH_PROFILE_BUCKET,
                utc_now(),
            )

        await asyncio.to_thread(update)

    async def load_profile_reference(self, archive_id: str) -> AuthProfileReference | None:
        run = await asyncio.to_thread(read_run, self.client, archive_id)

        return profile_reference_from_item(run) if run else None

    async def reconcile_abandoned(self, manager_id: str) -> None:
        def reconcile() -> None:
            cursor: dict[str, Any] | None = None

            while True:
                response = scan_sessions(self.client, cursor)

                for item in response.get("Items", []):
                    status = SessionStatus(string_from_item(item, "status", "auth session"))

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
                        fail_session(
                            self.client,
                            session,
                            new_status,
                            reason,
                            utc_now(),
                        )
                    except ClientError as error:
                        raise_unless_conditional_failure(error)

                cursor = response.get("LastEvaluatedKey")

                if not cursor:
                    return

        await asyncio.to_thread(reconcile)
