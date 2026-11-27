from fastapi import APIRouter, HTTPException, Request

from ..runtime import CaptureRuntime

HEALTH_CHECK_LIVENESS_PATH = "/health/live"
HEALTH_CHECK_READINESS_PATH = "/health/ready"

ARCHIVE_PAGES_PATH = "/archives/{archive_id}/pages"
ARCHIVE_SNAPSHOT_PATH = "/archives/{archive_id}/snapshots/{snapshot_id}"
ARCHIVE_WACZ_PATH = "/archives/{archive_id}/wacz"

router = APIRouter()


@router.get(HEALTH_CHECK_LIVENESS_PATH)
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get(HEALTH_CHECK_READINESS_PATH)
async def ready(request: Request) -> dict[str, str]:
    runtime: CaptureRuntime = request.app.state.runtime

    if not runtime.ready:
        raise HTTPException(status_code=503, detail="Capture runtime is not ready")

    return {"status": "ok"}
