from domain.capture import DEFAULT_AUTH_GENERATION, AuthContext
from ports.capture import AuthContextStore
from ports.login import AuthProfileStore, SessionStore


class StoredAuthContexts(AuthContextStore):
    def __init__(self, sessions: SessionStore, profiles: AuthProfileStore) -> None:
        self.sessions = sessions
        self.profiles = profiles

    async def load(self, archive_id: str) -> AuthContext:
        reference = await self.sessions.load_profile_reference(archive_id)

        if reference is None:
            return AuthContext(generation=DEFAULT_AUTH_GENERATION)

        storage_state = await self.profiles.load(reference.key)

        return AuthContext(generation=reference.generation, storage_state=storage_state)
