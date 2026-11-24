from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import FastAPI, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict
from websockets.asyncio.client import connect as connect_upstream
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from application import LoginManager, LoginUnavailable, SessionConflict, SessionNotFound
from assembly import LoginSettings
from domain import SessionRequest, SessionStatus

from .runtime import LoginRuntime as ConcreteLoginRuntime

WEB_DIRECTORY = Path(__file__).parent / "web"

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


class Runtime(Protocol):
    @property
    def ready(self) -> bool: ...

    @property
    def login_manager(self) -> LoginManager: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archiveId: str
    targetUrl: str


class UpdateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["COMPLETED", "CANCELLED"]


def app() -> FastAPI:
    return create_app(ConcreteLoginRuntime(LoginSettings.from_environment()))


def create_app(runtime: Runtime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        await runtime.start()

        try:
            yield
        finally:
            await runtime.stop()

    application = FastAPI(title="Castellani Capture Login", lifespan=lifespan)
    application.state.runtime = runtime

    @application.exception_handler(SessionNotFound)
    async def handle_not_found(_: Request, error: SessionNotFound) -> Response:
        return problem(
            404,
            "session-not-found",
            "Session Not Found",
            "The interactive session does not exist.",
        )

    @application.exception_handler(SessionConflict)
    async def handle_conflict(_: Request, error: SessionConflict) -> Response:
        return problem(
            409,
            "session-conflict",
            "Session Conflict",
            "The session cannot accept this request.",
        )

    @application.exception_handler(LoginUnavailable)
    async def handle_unavailable(_: Request, error: LoginUnavailable) -> Response:
        return problem(
            503,
            "login-unavailable",
            "Login Unavailable",
            "The interactive browser is not available. Start another session.",
        )

    @application.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready")
    async def ready(request: Request) -> dict[str, str]:
        runtime: Runtime = request.app.state.runtime

        if not runtime.ready:
            raise LoginUnavailable("login runtime is not ready")

        return {"status": "ok"}

    @application.post("/sessions", status_code=201)
    async def create_session(
        body: CreateSessionRequest,
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, object]:
        key = idempotency_key or ""

        if not valid_idempotency_key(key):
            raise SessionConflict("invalid idempotency key")

        session = await manager(request).create(
            SessionRequest(
                archive_id=body.archiveId,
                target_url=body.targetUrl,
            ),
            key,
        )

        return session.as_dict()

    @application.get("/sessions/{session_id}")
    async def get_session(session_id: str, request: Request) -> dict[str, object]:
        require_path_segment(session_id)

        session = await manager(request).get(session_id)

        return session.as_dict()

    @application.put("/sessions/{session_id}")
    async def update_session(
        session_id: str,
        body: UpdateSessionRequest,
        request: Request,
    ) -> dict[str, object]:
        require_path_segment(session_id)

        session = await manager(request).update(
            session_id,
            SessionStatus(body.status),
        )

        return session.as_dict()

    @application.get("/sessions/{session_id}/browser", response_class=HTMLResponse)
    async def browser(session_id: str, request: Request) -> str:
        require_path_segment(session_id)

        await manager(request).endpoint(session_id)

        return (WEB_DIRECTORY / "browser.html").read_text()

    @application.api_route(
        "/sessions/{session_id}/vnc/{asset_path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"],
    )
    async def vnc_asset(
        session_id: str,
        asset_path: str,
        request: Request,
    ) -> Response:
        require_path_segment(session_id)

        origin = await manager(request).endpoint(session_id)
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

    @application.websocket("/sessions/{session_id}/vnc/websockify")
    async def vnc_websocket(websocket: WebSocket, session_id: str) -> None:
        try:
            require_path_segment(session_id)
            origin = await manager(websocket).endpoint(session_id)
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

    return application


def manager(scope: Request | WebSocket) -> LoginManager:
    runtime: Runtime = scope.app.state.runtime

    return runtime.login_manager


def problem(status: int, kind: str, title: str, detail: str) -> Response:
    return Response(
        status_code=status,
        media_type="application/problem+json",
        content=(f'{{"type":"{kind}","title":"{title}","status":{status},"detail":"{detail}"}}'),
    )


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
