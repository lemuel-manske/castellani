from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from domain.capture import WACZObject
from problem import problem

from .routes import ARCHIVE_WACZ_PATH

router = APIRouter()

WACZ_MEDIA_TYPE = "application/wacz"


@router.get(ARCHIVE_WACZ_PATH)
async def get_wacz(archive_id: str, request: Request) -> Response:
    result = await read_wacz(archive_id, request, metadata_only=False)

    if isinstance(result, Response):
        return result

    if result.body is None:
        return problem(500, "internal", "Internal Server Error", "WACZ body is unavailable.")

    return StreamingResponse(
        result.body,
        status_code=status_code(result),
        media_type=WACZ_MEDIA_TYPE,
        headers=wacz_headers(result),
    )


@router.head(ARCHIVE_WACZ_PATH)
async def head_wacz(archive_id: str, request: Request) -> Response:
    result = await read_wacz(archive_id, request, metadata_only=True)

    if isinstance(result, Response):
        return result

    return Response(
        status_code=status_code(result),
        media_type=WACZ_MEDIA_TYPE,
        headers=wacz_headers(result),
    )


async def read_wacz(
    archive_id: str,
    request: Request,
    metadata_only: bool,
) -> WACZObject | Response:
    retrieval = request.app.state.runtime.archive_retrieval

    result = await retrieval.read_wacz(
        archive_id,
        request.headers.get("range"),
        request.headers.get("if-range"),
        metadata_only=metadata_only,
    )

    if result is None:
        return problem(
            404,
            "wacz-not-found",
            "WACZ Not Found",
            "No published WACZ exists for this archive.",
        )

    return result


def status_code(result: WACZObject) -> int:
    return 206 if result.partial else 200


def wacz_headers(result: WACZObject) -> dict[str, str]:
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(result.content_length),
        "ETag": result.etag,
    }

    if result.last_modified is not None:
        headers["Last-Modified"] = result.last_modified

    if result.content_range is not None:
        headers["Content-Range"] = result.content_range

    return headers
