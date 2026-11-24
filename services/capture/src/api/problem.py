from fastapi import Request
from fastapi.responses import JSONResponse, Response

from domain import InvalidArchiveCursor, InvalidWACZRange, WACZRangeNotSatisfiable

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ProblemResponse(JSONResponse):
    media_type = PROBLEM_MEDIA_TYPE


def problem(
    status: int,
    kind: str,
    title: str,
    detail: str,
    headers: dict[str, str] | None = None,
) -> ProblemResponse:
    return ProblemResponse(
        status_code=status,
        content={
            "type": kind,
            "title": title,
            "status": status,
            "detail": detail,
        },
        headers=headers,
    )


async def handle_archive_error(_: Request, error: Exception) -> Response:
    if isinstance(error, InvalidArchiveCursor):
        return problem(
            400,
            "invalid-cursor",
            "Invalid Cursor",
            "The pagination cursor is invalid for this archive.",
        )

    if isinstance(error, InvalidWACZRange):
        return problem(
            400,
            "invalid-range",
            "Invalid Range",
            "Only one valid byte range is supported.",
        )

    if isinstance(error, WACZRangeNotSatisfiable):
        return problem(
            416,
            "range-not-satisfiable",
            "Range Not Satisfiable",
            "The requested byte range is outside the published WACZ.",
            headers={"Content-Range": f"bytes */{error.content_length}"},
        )

    raise error
