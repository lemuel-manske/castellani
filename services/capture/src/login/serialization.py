from typing import Any

from domain.login import AuthSession


def auth_session_json(session: AuthSession) -> dict[str, Any]:
    result: dict[str, Any] = {
        "sessionId": session.session_id,
        "archiveId": session.archive_id,
        "status": str(session.status),
        "expiresAt": session.expires_at,
    }

    if session.auth_generation is not None:
        result["authGeneration"] = session.auth_generation

    return result
