from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response

from domain.login import LoginUnavailable, SessionConflict, SessionNotFound
from problem import problem
from utils.fn import noop

from .routes import Runtime, router
from .runtime import LoginRuntime as ConcreteLoginRuntime
from .settings import LoginSettings


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
        noop(error)

        return problem(
            404,
            "session-not-found",
            "Session Not Found",
            "The interactive session does not exist.",
        )

    @application.exception_handler(SessionConflict)
    async def handle_conflict(_: Request, error: SessionConflict) -> Response:
        noop(error)

        return problem(
            409,
            "session-conflict",
            "Session Conflict",
            "The session cannot accept this request.",
        )

    @application.exception_handler(LoginUnavailable)
    async def handle_unavailable(_: Request, error: LoginUnavailable) -> Response:
        noop(error)

        return problem(
            503,
            "login-unavailable",
            "Login Unavailable",
            "The interactive browser is not available. Start another session.",
        )

    application.include_router(router)

    return application
