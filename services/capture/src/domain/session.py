import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol


class SessionStatus(StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    FINALIZING = "FINALIZING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


TERMINAL_SESSION_STATUSES = frozenset(
    {
        SessionStatus.COMPLETED,
        SessionStatus.CANCELLED,
        SessionStatus.FAILED,
        SessionStatus.EXPIRED,
    }
)

ACTIVE_SESSION_STATUSES = frozenset(
    {
        SessionStatus.CREATED,
        SessionStatus.ACTIVE,
        SessionStatus.FINALIZING,
    }
)


@dataclass(frozen=True)
class AuthSession:
    session_id: str
    archive_id: str
    target_url: str
    status: SessionStatus
    expires_at: str
    manager_id: str
    version: int
    auth_generation: int | None = None
    profile_key: str | None = None
    vnc_origin: str | None = None
    failure_reason: str | None = None

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_SESSION_STATUSES

    def expired(self) -> bool:
        expires_at = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))

        return expires_at <= datetime.now(UTC)


@dataclass(frozen=True)
class SessionRequest:
    archive_id: str
    target_url: str


@dataclass(frozen=True)
class AuthProfileReference:
    generation: int
    key: str


@dataclass(frozen=True)
class BrowserEndpoint:
    session_id: str
    vnc_origin: str


class InteractiveBrowser(Protocol):
    async def start(self, session_id: str, target_url: str) -> BrowserEndpoint: ...

    async def storage_state(self, session_id: str) -> dict[str, Any]: ...

    async def close(self, session_id: str) -> None: ...


class SessionStore(Protocol):
    async def create(self, session: AuthSession, key: str, fingerprint: str) -> None: ...

    async def get(self, session_id: str) -> AuthSession | None: ...

    async def find_by_request(self, key: str, fingerprint: str) -> str | None: ...

    async def save(self, session: AuthSession) -> None: ...

    async def reserve_generation(self, archive_id: str) -> int: ...

    async def set_profile(self, archive_id: str, generation: int, key: str) -> None: ...

    async def load_profile_reference(self, archive_id: str) -> AuthProfileReference | None: ...

    async def reconcile_abandoned(self, manager_id: str) -> None: ...


class AuthProfileStore(Protocol):
    async def save(self, archive_id: str, generation: int, state: dict[str, Any]) -> str: ...

    async def load(self, key: str) -> dict[str, Any]: ...


def request_fingerprint(request: SessionRequest) -> str:
    payload = json.dumps(
        {"archiveId": request.archive_id, "targetUrl": request.target_url},
        separators=(",", ":"),
        sort_keys=True,
    )

    return hashlib.sha256(payload.encode()).hexdigest()
