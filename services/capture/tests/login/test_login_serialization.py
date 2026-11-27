from domain.login import AuthSession, SessionStatus
from login.serialization import auth_session_json


def test_auth_session_json_exposes_only_public_fields() -> None:
    session = AuthSession(
        session_id="session-1",
        archive_id="archive-1",
        target_url="https://example.org/",
        status=SessionStatus.ACTIVE,
        expires_at="2026-11-24T01:00:00Z",
        manager_id="manager-1",
        version=3,
        auth_generation=2,
        profile_key="secret",
    )

    assert auth_session_json(session) == {
        "sessionId": "session-1",
        "archiveId": "archive-1",
        "status": "ACTIVE",
        "expiresAt": "2026-11-24T01:00:00Z",
        "authGeneration": 2,
    }
