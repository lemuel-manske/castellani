from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from domain.capture import InvalidArchiveCursor, InvalidWACZRange, WACZRangeNotSatisfiable

from ..runtime import CaptureRuntime
from ..settings import CaptureSettings
from .metadata import router as metadata_router
from .problem import handle_archive_error
from .routes import router as health_router
from .wacz import router as wacz_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    runtime = CaptureRuntime(CaptureSettings.from_environment())

    await runtime.start()

    app.state.runtime = runtime

    try:
        yield
    finally:
        await runtime.stop()


def app() -> FastAPI:
    application = FastAPI(title="Castellani Capture", lifespan=lifespan)

    application.add_exception_handler(InvalidArchiveCursor, handle_archive_error)
    application.add_exception_handler(InvalidWACZRange, handle_archive_error)
    application.add_exception_handler(WACZRangeNotSatisfiable, handle_archive_error)

    application.include_router(metadata_router)
    application.include_router(wacz_router)
    application.include_router(health_router)

    return application
