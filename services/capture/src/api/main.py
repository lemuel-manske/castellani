from fastapi import FastAPI

HEALTH_CHECK_PATH = "/health"
HEALTH_CHECK_LIVENESS_PATH = f"{HEALTH_CHECK_PATH}/live"
HEALTH_CHECK_READINESS_PATH = f"{HEALTH_CHECK_PATH}/ready"

app = FastAPI(title="Castellani Capture")


@app.get(HEALTH_CHECK_LIVENESS_PATH)
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get(HEALTH_CHECK_READINESS_PATH)
async def ready() -> dict[str, str]:
    return {"status": "ok"}
