from fastapi import Request
from fastapi.responses import Response

from domain.capture import InvalidArchiveCursor, InvalidWACZRange, WACZRangeNotSatisfiable
from problem import problem


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
