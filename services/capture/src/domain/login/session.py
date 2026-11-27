import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


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

    def fingerprint(self) -> str:
        payload = json.dumps(
            {"archiveId": self.archive_id, "targetUrl": self.target_url},
            separators=(",", ":"),
            sort_keys=True,
        )

        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class AuthProfileReference:
    generation: int
    key: str


@dataclass(frozen=True)
class BrowserEndpoint:
    session_id: str
    vnc_origin: str
