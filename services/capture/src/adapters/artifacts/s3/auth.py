from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ports.login import AuthProfileCipher, AuthProfileStore
from topology.buckets import AUTH_PROFILE_BUCKET

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client


class S3AuthProfileStore(AuthProfileStore):
    def __init__(self, s3_client: S3Client, cipher: AuthProfileCipher) -> None:
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
