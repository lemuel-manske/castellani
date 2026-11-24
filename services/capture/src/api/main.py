from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from assembly import CaptureRuntime, CaptureSettings
from domain import InvalidArchiveCursor, InvalidWACZRange, WACZRangeNotSatisfiable

from .metadata import router as metadata_router
from .problem import handle_archive_error
from .routes import HEALTH_CHECK_LIVENESS_PATH, HEALTH_CHECK_READINESS_PATH
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


app = FastAPI(title="Castellani Capture", lifespan=lifespan)

app.add_exception_handler(InvalidArchiveCursor, handle_archive_error)
app.add_exception_handler(InvalidWACZRange, handle_archive_error)
app.add_exception_handler(WACZRangeNotSatisfiable, handle_archive_error)

app.include_router(metadata_router)
app.include_router(wacz_router)


@app.get(HEALTH_CHECK_LIVENESS_PATH)
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get(HEALTH_CHECK_READINESS_PATH)
async def ready(request: Request) -> dict[str, str]:
    runtime: CaptureRuntime | None = getattr(request.app.state, "runtime", None)

    if runtime is None or not runtime.ready:
        raise HTTPException(status_code=503, detail="Capture runtime is not ready")

    return {"status": "ok"}
