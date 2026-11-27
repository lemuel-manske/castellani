from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict
from websockets.asyncio.client import connect as connect_upstream
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from application.login import LoginManager
from domain.login import (
    LoginUnavailable,
    SessionConflict,
    SessionNotFound,
    SessionRequest,
    SessionStatus,
)
from login.runtime import LoginRuntime

from .serialization import auth_session_json

WEB_DIRECTORY = Path(__file__).parent / "web"

HEALTH_CHECK_LIVENESS_PATH = "/health/live"
HEALTH_CHECK_READINESS_PATH = "/health/ready"
SESSIONS_PATH = "/sessions"
SESSION_PATH = "/sessions/{session_id}"
SESSION_BROWSER_PATH = "/sessions/{session_id}/browser"
VNC_ASSET_PATH = "/sessions/{session_id}/vnc/{asset_path:path}"
VNC_WEBSOCKET_PATH = "/sessions/{session_id}/vnc/websockify"

MIN_KEY_LENGTH = 8
MAX_KEY_LENGTH = 200

FORBIDDEN_PATH_CHARACTERS = "/\\?#"

FORWARDED_REQUEST_HEADERS = (
    "accept",
    "accept-encoding",
    "cache-control",
    "content-type",
    "if-modified-since",
    "if-none-match",
    "range",
)

FORWARDED_RESPONSE_HEADERS = (
    "accept-ranges",
    "cache-control",
    "content-length",
    "content-range",
    "content-type",
    "etag",
    "last-modified",
)


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archiveId: str
    targetUrl: str


class UpdateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["COMPLETED", "CANCELLED"]


router = APIRouter()


@router.get(HEALTH_CHECK_LIVENESS_PATH)
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get(HEALTH_CHECK_READINESS_PATH)
async def ready(request: Request) -> dict[str, str]:
    runtime: LoginRuntime = request.app.state.runtime

    if not runtime.ready:
        raise LoginUnavailable("login runtime is not ready")

    return {"status": "ok"}


@router.post(SESSIONS_PATH, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    key = idempotency_key or ""

    if not valid_idempotency_key(key):
        raise SessionConflict("invalid idempotency key")

    login_manager: LoginManager = request.app.state.manager

    session = await login_manager.create(
        SessionRequest(
            archive_id=body.archiveId,
            target_url=body.targetUrl,
        ),
        key,
    )

    return auth_session_json(session)


@router.get(SESSION_PATH)
async def get_session(session_id: str, request: Request) -> dict[str, object]:
    require_path_segment(session_id)

    login_manager: LoginManager = request.app.state.manager

    session = await login_manager.get(session_id)

    return auth_session_json(session)


@router.put(SESSION_PATH)
async def update_session(
    session_id: str,
    body: UpdateSessionRequest,
    request: Request,
) -> dict[str, object]:
    require_path_segment(session_id)

    login_manager: LoginManager = request.app.state.manager

    session = await login_manager.update(
        session_id,
        SessionStatus(body.status),
    )

    return auth_session_json(session)


@router.get(SESSION_BROWSER_PATH, response_class=HTMLResponse)
async def browser(session_id: str, request: Request) -> str:
    require_path_segment(session_id)

    login_manager: LoginManager = request.app.state.manager

    await login_manager.endpoint(session_id)

    return (WEB_DIRECTORY / "browser.html").read_text()


@router.api_route(
    VNC_ASSET_PATH,
    methods=["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"],
)
async def vnc_asset(
    session_id: str,
    asset_path: str,
    request: Request,
) -> Response:
    require_path_segment(session_id)

    login_manager: LoginManager = request.app.state.manager

    origin = await login_manager.endpoint(session_id)

    target = f"{origin}/{asset_path}"

    async with httpx.AsyncClient(timeout=None) as client:
        upstream = await client.request(
            request.method,
            target,
            params=dict(request.query_params),
            content=await request.body(),
            headers={
                name: value
                for name, value in request.headers.items()
                if name.lower() in FORWARDED_REQUEST_HEADERS
            },
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={
            name: value
            for name, value in upstream.headers.items()
            if name.lower() in FORWARDED_RESPONSE_HEADERS
        },
    )


@router.websocket(VNC_WEBSOCKET_PATH)
async def vnc_websocket(websocket: WebSocket, session_id: str) -> None:
    login_manager: LoginManager = websocket.app.state.manager

    try:
        require_path_segment(session_id)

        origin = await login_manager.endpoint(session_id)
    except (LoginUnavailable, SessionConflict, SessionNotFound, ValueError):
        await websocket.close(code=1008, reason="Session is not available")

        return

    target = urlsplit(origin)
    upstream_url = urlunsplit(
        (
            "wss" if target.scheme == "https" else "ws",
            target.netloc,
            "/websockify",
            websocket.url.query,
            "",
        )
    )

    try:
        async with connect_upstream(
            upstream_url,
            open_timeout=10,
        ) as upstream:
            response = upstream.response
            subprotocol = response.headers.get("sec-websocket-protocol") if response else None

            await websocket.accept(subprotocol=subprotocol)

            async def from_client() -> None:
                while True:
                    message = await websocket.receive()

                    if message["type"] == "websocket.disconnect":
                        return

                    if message.get("text") is not None:
                        await upstream.send(message["text"])
                    elif message.get("bytes") is not None:
                        await upstream.send(message["bytes"])

            async def from_upstream() -> None:
                async for message in upstream:
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_bytes(message)

            tasks = [
                asyncio.create_task(from_client()),
                asyncio.create_task(from_upstream()),
            ]

            pending: set[asyncio.Task[None]] = set()

            try:
                _, pending = await asyncio.wait(
                    tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                for task in pending:
                    task.cancel()

                await asyncio.gather(*tasks, return_exceptions=True)
    except (
        ConnectionClosed,
        InvalidHandshake,
        OSError,
        TimeoutError,
        WebSocketDisconnect,
    ):
        return


def valid_idempotency_key(key: str | None) -> bool:
    if key is None:
        return False

    return (
        MIN_KEY_LENGTH <= len(key) <= MAX_KEY_LENGTH
        and key.strip() == key
        and not any(character in key for character in "\r\n\x00")
    )


def valid_path_segment(value: str) -> bool:
    return value not in {"", ".", ".."} and not any(
        character in value for character in FORBIDDEN_PATH_CHARACTERS
    )


def require_path_segment(value: str) -> None:
    if not valid_path_segment(value):
        raise SessionConflict("invalid session id")
