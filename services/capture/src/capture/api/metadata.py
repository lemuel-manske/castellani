from fastapi import APIRouter, Request
from fastapi.responses import Response

from problem import problem

from .routes import ARCHIVE_PAGES_PATH, ARCHIVE_SNAPSHOT_PATH
from .serialization import page_listing_json, snapshot_reference_json
from .types import JSON

router = APIRouter()

DEFAULT_PAGE_LIMIT = 25

MAX_PAGE_LIMIT = 100


@router.get(ARCHIVE_PAGES_PATH, response_model=None)
async def list_pages(archive_id: str, request: Request) -> JSON | Response:
    raw_limit = request.query_params.get("limit")

    if raw_limit is None:
        limit = DEFAULT_PAGE_LIMIT
    else:
        try:
            limit = int(raw_limit)
        except ValueError:
            return problem(
                400, "invalid-pagination", "Invalid Pagination", "limit must be an integer"
            )

        if limit < 1 or limit > MAX_PAGE_LIMIT:
            return problem(
                400,
                "invalid-pagination",
                "Invalid Pagination",
                "limit must be between 1 and 100",
            )

    retrieval = request.app.state.runtime.archive_retrieval

    listing = await retrieval.list_pages(
        archive_id,
        limit,
        request.query_params.get("cursor"),
    )

    return page_listing_json(listing)


@router.get(ARCHIVE_SNAPSHOT_PATH, response_model=None)
async def get_snapshot(
    archive_id: str,
    snapshot_id: str,
    request: Request,
) -> JSON | Response:
    retrieval = request.app.state.runtime.archive_retrieval

    snapshot = await retrieval.read_snapshot(archive_id, snapshot_id)

    if snapshot is None:
        return problem(
            404,
            "snapshot-not-found",
            "Snapshot Not Found",
            "The requested snapshot does not exist for this archive.",
        )

    return snapshot_reference_json(snapshot)
