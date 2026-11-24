from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from application import SessionConflict
from assembly import auth_session_json
from domain import AuthSession, SessionStatus
from login.api import create_app

SESSION_ID = "session-1"


def test_create_session_returns_only_public_session_metadata() -> None:
    manager = RecordingManager(new_session())

    with TestClient(create_app(FakeRuntime(manager))) as client:
        response = client.post(
            "/sessions",
            json={
                "archiveId": "archive-1",
                "targetUrl": "https://example.org/",
            },
            headers={"Idempotency-Key": "idempotency-1"},
        )

    assert (response.status_code, response.json()) == (201, auth_session_json(manager.session))


def test_create_session_rejects_a_missing_idempotency_key() -> None:
    with TestClient(create_app(FakeRuntime(RecordingManager(new_session())))) as client:
        response = client.post(
            "/sessions",
            json={
                "archiveId": "archive-1",
                "targetUrl": "https://example.org/",
            },
        )

    assert (response.status_code, response.json()["type"]) == (409, "session-conflict")


def test_get_session_returns_the_current_state() -> None:
    session = new_session()
    manager = RecordingManager(session)

    with TestClient(create_app(FakeRuntime(manager))) as client:
        response = client.get(f"/sessions/{SESSION_ID}")

    assert (response.status_code, response.json()) == (200, auth_session_json(session))


def test_get_session_rejects_an_invalid_session_id() -> None:
    with TestClient(create_app(FakeRuntime(RecordingManager(new_session())))) as client:
        response = client.get("/sessions/%2e%2e")

    assert (response.status_code, response.json()["type"]) == (409, "session-conflict")


def test_update_session_finalizes_an_active_session() -> None:
    manager = RecordingManager(new_session())

    with TestClient(create_app(FakeRuntime(manager))) as client:
        response = client.put(
            f"/sessions/{SESSION_ID}",
            json={"status": "COMPLETED"},
        )

    assert (
        response.status_code,
        response.json()["status"],
        manager.updates,
    ) == (200, "COMPLETED", [SessionStatus.COMPLETED])


def test_update_session_rejects_an_unsupported_transition() -> None:
    with TestClient(create_app(FakeRuntime(RecordingManager(new_session())))) as client:
        response = client.put(
            f"/sessions/{SESSION_ID}",
            json={"status": "ACTIVE"},
        )

    assert response.status_code == 422


def test_browser_page_is_served_for_a_live_session() -> None:
    with TestClient(create_app(FakeRuntime(RecordingManager(new_session())))) as client:
        response = client.get(f"/sessions/{SESSION_ID}/browser")

    assert (response.status_code, response.headers["content-type"]) == (
        200,
        "text/html; charset=utf-8",
    )


def test_vnc_websocket_rejects_a_session_without_a_live_browser() -> None:
    manager = RecordingManager(new_session(status=SessionStatus.COMPLETED))

    with TestClient(create_app(FakeRuntime(manager))) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(f"/sessions/{SESSION_ID}/vnc/websockify"):
                pass

    assert (error.value.code, error.value.reason) == (1008, "Session is not available")


def test_ready_reports_an_unstarted_runtime() -> None:
    runtime = FakeRuntime(RecordingManager(new_session()), ready=False)

    with TestClient(create_app(runtime)) as client:
        response = client.get("/health/ready")

    assert (response.status_code, response.json()["type"]) == (
        503,
        "login-unavailable",
    )


def new_session(status: SessionStatus = SessionStatus.ACTIVE) -> AuthSession:
    expires_at = datetime.now(UTC) + timedelta(seconds=1800)

    return AuthSession(
        session_id=SESSION_ID,
        archive_id="archive-1",
        target_url="https://example.org/",
        status=status,
        expires_at=expires_at.isoformat().replace("+00:00", "Z"),
        manager_id="manager-1",
        version=1,
        vnc_origin="http://127.0.0.1:6080",
    )


class FakeRuntime:
    def __init__(self, manager: RecordingManager, ready: bool = True) -> None:
        self.manager = manager
        self._ready = ready

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def login_manager(self) -> Any:
        return self.manager

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class RecordingManager:
    def __init__(self, session: AuthSession) -> None:
        self.session = session
        self.updates: list[SessionStatus] = []

    async def create(self, request: Any, key: str) -> AuthSession:
        return self.session

    async def get(self, session_id: str) -> AuthSession:
        return self.session

    async def update(self, session_id: str, status: SessionStatus) -> AuthSession:
        self.updates.append(status)
        self.session = replace(self.session, status=status)

        return self.session

    async def endpoint(self, session_id: str) -> str:
        if self.session.terminal or not self.session.vnc_origin:
            raise SessionConflict("session has no live browser")

        return self.session.vnc_origin
