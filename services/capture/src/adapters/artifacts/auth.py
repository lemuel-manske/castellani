import asyncio
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from domain.login import AuthProfileStore
from topology.buckets import AUTH_PROFILE_BUCKET

NONCE_BYTES = 12

KEY_ENCODING = "utf-8"


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


class EncryptedAuthProfileStore(AuthProfileStore):
    def __init__(self, s3_client: Any, cipher: AuthProfileCipher) -> None:
        self.s3_client = s3_client
        self.cipher = cipher

    async def save(self, archive_id: str, generation: int, state: dict[str, Any]) -> str:
        key = f"auth-profiles/{archive_id}/generation-{generation}.json.enc"
        ciphertext = self.cipher.encrypt(state)

        def put() -> None:
            self.s3_client.put_object(
                Bucket=AUTH_PROFILE_BUCKET,
                Key=key,
                Body=ciphertext,
                ContentType="application/octet-stream",
                Metadata={"auth-generation": str(generation)},
            )

        await asyncio.to_thread(put)

        return key

    async def load(self, key: str) -> dict[str, Any]:
        def get() -> bytes:
            response = self.s3_client.get_object(Bucket=AUTH_PROFILE_BUCKET, Key=key)
            body = response["Body"]

            try:
                return body.read()
            finally:
                body.close()

        ciphertext = await asyncio.to_thread(get)

        return self.cipher.decrypt(ciphertext)
