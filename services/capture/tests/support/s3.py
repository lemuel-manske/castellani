from pathlib import Path
from typing import Any


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, dict[str, str]]] = {}

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        ExtraArgs: dict[str, Any],
    ) -> None:
        self.objects[(bucket, key)] = (
            Path(filename).read_bytes(),
            ExtraArgs["Metadata"],
        )

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        body, metadata = self.objects[(Bucket, Key)]
        return {
            "ContentLength": len(body),
            "Metadata": metadata,
            "VersionId": "version-1",
        }
