import json
import os
from abc import ABC, abstractmethod
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from domain.login import AuthProfileReference, AuthSession, BrowserEndpoint

NONCE_BYTES = 12

KEY_ENCODING = "utf-8"


class InteractiveBrowser(ABC):
    @abstractmethod
    async def start(self, session_id: str, target_url: str) -> BrowserEndpoint: ...

    @abstractmethod
    async def storage_state(self, session_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def close(self, session_id: str) -> None: ...


class SessionStore(ABC):
    @abstractmethod
    async def create(self, session: AuthSession, key: str, fingerprint: str) -> None: ...

    @abstractmethod
    async def get(self, session_id: str) -> AuthSession | None: ...

    @abstractmethod
    async def find_by_request(self, key: str, fingerprint: str) -> str | None: ...

    @abstractmethod
    async def save(self, session: AuthSession) -> None: ...

    @abstractmethod
    async def reserve_generation(self, archive_id: str) -> int: ...

    @abstractmethod
    async def set_profile(self, archive_id: str, generation: int, key: str) -> None: ...

    @abstractmethod
    async def load_profile_reference(
        self,
        archive_id: str,
    ) -> AuthProfileReference | None: ...

    @abstractmethod
    async def reconcile_abandoned(self, manager_id: str) -> None: ...


class AuthProfileStore(ABC):
    @abstractmethod
    async def save(self, archive_id: str, generation: int, state: dict[str, Any]) -> str: ...

    @abstractmethod
    async def load(self, key: str) -> dict[str, Any]: ...


class AuthProfileCipher:
    def __init__(self, key: bytes) -> None:
        self.aead = AESGCM(key)

    def encrypt(self, state: dict[str, Any]) -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        payload = json.dumps(
            state,
            separators=(",", ":"),
            sort_keys=True,
        ).encode(KEY_ENCODING)

        return nonce + self.aead.encrypt(nonce, payload, None)

    def decrypt(self, ciphertext: bytes) -> dict[str, Any]:
        payload = self.aead.decrypt(
            ciphertext[:NONCE_BYTES],
            ciphertext[NONCE_BYTES:],
            None,
        )

        result: dict[str, Any] = json.loads(payload.decode(KEY_ENCODING))

        return result
