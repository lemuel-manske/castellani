from fastapi.responses import JSONResponse

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
