from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from application import (
    DuplicateSessionRequest,
    LoginManager,
    LoginUnavailable,
    SessionConflict,
    SessionNotFound,
)
from domain import (
    AuthProfileReference,
    AuthProfileStore,
    AuthSession,
    BrowserEndpoint,
    InteractiveBrowser,
    SessionRequest,
    SessionStatus,
    SessionStore,
)

REQUEST = SessionRequest("archive-1", "https://example.org/")


async def test_create_starts_a_live_browser_and_persists_an_active_session() -> None:
    sessions = MemorySessionStore()
    browser = MemoryBrowser()

    session = await login_manager(sessions, browser).create(REQUEST, "idempotency-1")

    assert (
        session.status,
        session.manager_id,
        browser.sessions,
    ) == (SessionStatus.ACTIVE, "manager-1", {session.session_id})


async def test_create_is_idempotent_for_the_same_key_and_request() -> None:
    sessions = MemorySessionStore()
    manager = login_manager(sessions, MemoryBrowser())

    first = await manager.create(REQUEST, "idempotency-1")
    second = await manager.create(REQUEST, "idempotency-1")

    assert second.session_id == first.session_id


async def test_create_is_idempotent_when_an_idempotency_race_is_lost() -> None:
    sessions = MemorySessionStore()
    manager = login_manager(sessions, MemoryBrowser())

    first = await manager.create(REQUEST, "idempotency-1")
    sessions.hide_request_once = True
    sessions.duplicate_once = True
    second = await manager.create(REQUEST, "idempotency-1")

    assert second.session_id == first.session_id


async def test_create_rejects_a_known_key_with_a_different_request() -> None:
    manager = login_manager(MemorySessionStore(), MemoryBrowser())

    await manager.create(REQUEST, "idempotency-1")

    with pytest.raises(SessionConflict):
        await manager.create(
            SessionRequest("archive-1", "https://example.org/other"),
            "idempotency-1",
        )


async def test_create_marks_the_session_failed_when_the_browser_cannot_start() -> None:
    sessions = MemorySessionStore()
    browser = MemoryBrowser(start_error=RuntimeError("Xvfb unavailable"))

    with pytest.raises(LoginUnavailable):
        await login_manager(sessions, browser).create(REQUEST, "idempotency-1")

    assert [session.status for session in sessions.sessions.values()] == [SessionStatus.FAILED]


async def test_get_expires_an_abandoned_session_and_closes_its_browser() -> None:
    sessions = MemorySessionStore()
    browser = MemoryBrowser()
    manager = login_manager(sessions, browser)

    created = await manager.create(REQUEST, "idempotency-1")
    stored = sessions.sessions[created.session_id]
    sessions.sessions[created.session_id] = replace(
        stored,
        expires_at=past(),
    )

    expired = await manager.get(created.session_id)

    assert (expired.status, browser.sessions) == (SessionStatus.EXPIRED, set())


async def test_get_rejects_an_unknown_session() -> None:
    with pytest.raises(SessionNotFound):
        await login_manager(MemorySessionStore(), MemoryBrowser()).get("missing")


async def test_finalize_stores_one_generation_and_closes_the_browser() -> None:
    sessions = MemorySessionStore()
    profiles = MemoryProfiles()
    browser = MemoryBrowser()
    manager = login_manager(sessions, browser, profiles)

    created = await manager.create(REQUEST, "idempotency-1")
    completed = await manager.finalize(created.session_id)

    assert (
        completed.status,
        completed.auth_generation,
        sessions.profile,
        browser.sessions,
    ) == (
        SessionStatus.COMPLETED,
        1,
        ("archive-1", 1, "auth-profiles/archive-1/generation-1.json.enc"),
        set(),
    )


async def test_finalize_is_idempotent_for_a_completed_session() -> None:
    manager = login_manager(MemorySessionStore(), MemoryBrowser(), MemoryProfiles())

    created = await manager.create(REQUEST, "idempotency-1")
    first = await manager.finalize(created.session_id)
    second = await manager.finalize(created.session_id)

    assert second == first


async def test_finalize_rejects_a_cancelled_session() -> None:
    manager = login_manager(MemorySessionStore(), MemoryBrowser(), MemoryProfiles())

    created = await manager.create(REQUEST, "idempotency-1")
    await manager.cancel(created.session_id)

    with pytest.raises(SessionConflict):
        await manager.finalize(created.session_id)


async def test_finalize_marks_the_session_failed_when_profile_storage_fails() -> None:
    sessions = MemorySessionStore()
    browser = MemoryBrowser()
    profiles = MemoryProfiles(save_error=RuntimeError("S3 unavailable"))
    manager = login_manager(sessions, browser, profiles)

    created = await manager.create(REQUEST, "idempotency-1")

    with pytest.raises(LoginUnavailable):
        await manager.finalize(created.session_id)

    assert (
        sessions.sessions[created.session_id].status,
        browser.sessions,
    ) == (SessionStatus.FAILED, set())


async def test_start_reconciles_sessions_abandoned_by_another_manager() -> None:
    sessions = MemorySessionStore()
    sessions.sessions["session-1"] = new_session(manager_id="previous-manager")
    manager = login_manager(sessions, MemoryBrowser(), manager_id="manager-2")

    await manager.start()

    assert sessions.sessions["session-1"].status == SessionStatus.FAILED


async def test_endpoint_rejects_a_terminal_session() -> None:
    manager = login_manager(MemorySessionStore(), MemoryBrowser(), MemoryProfiles())

    created = await manager.create(REQUEST, "idempotency-1")
    await manager.cancel(created.session_id)

    with pytest.raises(SessionConflict):
        await manager.endpoint(created.session_id)


def login_manager(
    sessions: SessionStore,
    browser: InteractiveBrowser,
    profiles: AuthProfileStore | None = None,
    manager_id: str = "manager-1",
) -> LoginManager:
    return LoginManager(
        sessions=sessions,
        browser=browser,
        profiles=profiles or MemoryProfiles(),
        manager_id=manager_id,
        session_ttl_seconds=1800,
    )


def new_session(manager_id: str = "manager-1") -> AuthSession:
    return AuthSession(
        session_id="session-1",
        archive_id="archive-1",
        target_url="https://example.org/",
        status=SessionStatus.ACTIVE,
        expires_at=future(),
        manager_id=manager_id,
        version=1,
    )


def past() -> str:
    value = datetime.now(UTC) - timedelta(seconds=1)

    return value.isoformat().replace("+00:00", "Z")


def future() -> str:
    value = datetime.now(UTC) + timedelta(seconds=1800)

    return value.isoformat().replace("+00:00", "Z")


class MemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self.sessions: dict[str, AuthSession] = {}
        self.requests: dict[str, tuple[str, str]] = {}
        self.generation = 0
        self.profile: tuple[str, int, str] | None = None
        self.hide_request_once = False
        self.duplicate_once = False

    async def create(self, session: AuthSession, key: str, fingerprint: str) -> None:
        if session.session_id in self.sessions or key in self.requests:
            raise DuplicateSessionRequest

        if self.duplicate_once:
            self.duplicate_once = False
            raise DuplicateSessionRequest

        self.sessions[session.session_id] = session
        self.requests[key] = (session.session_id, fingerprint)

    async def get(self, session_id: str) -> AuthSession | None:
        return self.sessions.get(session_id)

    async def find_by_request(self, key: str, fingerprint: str) -> str | None:
        if self.hide_request_once:
            self.hide_request_once = False
            return None

        found = self.requests.get(key)

        if found is None:
            return None

        if found[1] != fingerprint:
            raise SessionConflict("idempotency key was reused with a different body")

        return found[0]

    async def save(self, session: AuthSession) -> None:
        current = self.sessions.get(session.session_id)

        if current is None or current.version != session.version - 1:
            raise SessionConflict("stale session version")

        self.sessions[session.session_id] = session

    async def reserve_generation(self, archive_id: str) -> int:
        self.generation += 1

        return self.generation

    async def set_profile(self, archive_id: str, generation: int, key: str) -> None:
        self.profile = (archive_id, generation, key)

    async def load_profile_reference(self, archive_id: str) -> AuthProfileReference | None:
        if self.profile is None or self.profile[0] != archive_id:
            return None

        return AuthProfileReference(generation=self.profile[1], key=self.profile[2])

    async def reconcile_abandoned(self, manager_id: str) -> None:
        for session_id, session in tuple(self.sessions.items()):
            if session.terminal or session.manager_id == manager_id:
                continue

            self.sessions[session_id] = replace(
                session,
                status=SessionStatus.FAILED,
                version=session.version + 1,
                failure_reason="login manager restarted",
            )


class MemoryBrowser(InteractiveBrowser):
    def __init__(self, start_error: Exception | None = None) -> None:
        self.start_error = start_error
        self.sessions: set[str] = set()
        self.closed: list[str] = []

    async def start(self, session_id: str, target_url: str) -> BrowserEndpoint:
        if self.start_error is not None:
            raise self.start_error

        self.sessions.add(session_id)

        return BrowserEndpoint(session_id, f"http://127.0.0.1:{6080 + len(self.sessions)}")

    async def storage_state(self, session_id: str) -> dict[str, Any]:
        return {"cookies": [], "origins": []}

    async def close(self, session_id: str) -> None:
        self.sessions.discard(session_id)
        self.closed.append(session_id)


class MemoryProfiles(AuthProfileStore):
    def __init__(self, save_error: Exception | None = None) -> None:
        self.save_error = save_error
        self.saved: dict[int, dict[str, Any]] = {}

    async def save(
        self,
        archive_id: str,
        generation: int,
        state: dict[str, Any],
    ) -> str:
        if self.save_error is not None:
            raise self.save_error

        self.saved[generation] = state

        return f"auth-profiles/{archive_id}/generation-{generation}.json.enc"

    async def load(self, key: str) -> dict[str, Any]:
        return self.saved[1]
