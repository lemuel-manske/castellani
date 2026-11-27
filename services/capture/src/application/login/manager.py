import secrets
from datetime import timedelta
from typing import Any

from domain.login import (
    AuthSession,
    DuplicateSessionRequest,
    LoginUnavailable,
    SessionConflict,
    SessionNotFound,
    SessionRequest,
    SessionStatus,
)
from ports.login import AuthProfileStore, InteractiveBrowser, SessionStore
from utils.time import utc_now

SESSION_ID_BYTES = 24


def replace_session(session: AuthSession, **changes: object) -> AuthSession:
    values: dict[str, Any] = {
        **session.__dict__,
        "version": session.version + 1,
        **changes,
    }

    return AuthSession(**values)


class LoginManager:
    def __init__(
        self,
        sessions: SessionStore,
        browser: InteractiveBrowser,
        profiles: AuthProfileStore,
        manager_id: str,
        session_ttl_seconds: int,
    ) -> None:
        self.sessions = sessions
        self.browser = browser
        self.profiles = profiles
        self.manager_id = manager_id
        self.session_ttl_seconds = session_ttl_seconds

    async def start(self) -> None:
        await self.sessions.reconcile_abandoned(self.manager_id)

    async def create(self, request: SessionRequest, key: str) -> AuthSession:
        fingerprint = request.fingerprint()

        existing_id = await self.sessions.find_by_request(key, fingerprint)

        if existing_id is not None:
            session = await self.sessions.get(existing_id)

            if session is None:
                raise SessionNotFound(existing_id)

            return session

        session = AuthSession(
            session_id=secrets.token_urlsafe(SESSION_ID_BYTES),
            archive_id=request.archive_id,
            target_url=request.target_url,
            status=SessionStatus.CREATED,
            expires_at=utc_now(timedelta(self.session_ttl_seconds)),
            manager_id=self.manager_id,
            version=1,
        )

        try:
            await self.sessions.create(session, key, fingerprint)
        except DuplicateSessionRequest as error:
            existing_id = await self.sessions.find_by_request(key, fingerprint)

            if existing_id is None:
                raise SessionConflict(
                    "idempotency key was reused concurrently",
                ) from error

            existing = await self.sessions.get(existing_id)

            if existing is None:
                raise SessionNotFound(existing_id) from error

            return existing

        try:
            endpoint = await self.browser.start(session.session_id, session.target_url)
        except Exception as error:
            failed = replace_session(
                session,
                status=SessionStatus.FAILED,
                failure_reason="interactive browser could not start",
            )

            await self.sessions.save(failed)

            raise LoginUnavailable("interactive browser could not start") from error

        active = replace_session(
            session,
            status=SessionStatus.ACTIVE,
            vnc_origin=endpoint.vnc_origin,
        )

        try:
            await self.sessions.save(active)
        except Exception:
            await self.browser.close(session.session_id)

            raise

        return active

    async def get(self, session_id: str) -> AuthSession:
        session = await self.sessions.get(session_id)

        if session is None:
            raise SessionNotFound(session_id)

        if not session.terminal and session.expired():
            expired = replace_session(
                session,
                status=SessionStatus.EXPIRED,
                failure_reason="session expired",
            )

            await self.sessions.save(expired)
            await self.browser.close(session_id)

            return expired

        return session

    async def endpoint(self, session_id: str) -> str:
        session = await self.get(session_id)

        if session.terminal or not session.vnc_origin:
            raise SessionConflict("session has no live browser")

        return session.vnc_origin

    async def update(self, session_id: str, status: SessionStatus) -> AuthSession:
        if status == SessionStatus.COMPLETED:
            return await self.finalize(session_id)

        if status == SessionStatus.CANCELLED:
            return await self.cancel(session_id)

        raise SessionConflict("unsupported session transition")

    async def finalize(self, session_id: str) -> AuthSession:
        session = await self.get(session_id)

        if session.terminal:
            if session.status == SessionStatus.COMPLETED:
                return session

            raise SessionConflict("session is already closed")

        if session.status != SessionStatus.ACTIVE:
            raise SessionConflict("session is not ready for completion")

        finalizing = replace_session(session, status=SessionStatus.FINALIZING)

        await self.sessions.save(finalizing)

        try:
            state = await self.browser.storage_state(session_id)

            generation = await self.sessions.reserve_generation(session.archive_id)

            profile_key = await self.profiles.save(session.archive_id, generation, state)

            await self.sessions.set_profile(session.archive_id, generation, profile_key)
        except Exception as error:
            failed = replace_session(
                finalizing,
                status=SessionStatus.FAILED,
                failure_reason="authentication state could not be stored",
            )

            await self.sessions.save(failed)
            await self.browser.close(session_id)

            raise LoginUnavailable("authentication state could not be stored") from error

        completed = replace_session(
            finalizing,
            status=SessionStatus.COMPLETED,
            auth_generation=generation,
            profile_key=profile_key,
        )

        await self.sessions.save(completed)
        await self.browser.close(session_id)

        return completed

    async def cancel(self, session_id: str) -> AuthSession:
        session = await self.get(session_id)

        if session.terminal:
            if session.status == SessionStatus.CANCELLED:
                return session

            raise SessionConflict("session is already closed")

        cancelled = replace_session(session, status=SessionStatus.CANCELLED)

        await self.sessions.save(cancelled)
        await self.browser.close(session_id)

        return cancelled
