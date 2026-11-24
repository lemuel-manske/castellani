from datetime import datetime
from pathlib import Path
from typing import Any


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, dict[str, str]]] = {}
        self.responses: dict[tuple[str, str], dict[str, Any]] = {}

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

    def put_object(
        self,
        Bucket: str,
        Key: str,
        Body: bytes,
        ETag: str,
        LastModified: datetime,
    ) -> None:
        self.objects[(Bucket, Key)] = (Body, {})
        self.responses[(Bucket, Key)] = {
            "ETag": ETag,
            "LastModified": LastModified,
        }

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        body, metadata = self.objects[(Bucket, Key)]

        response: dict[str, Any] = {
            "ContentLength": len(body),
            "Metadata": metadata,
            "VersionId": "version-1",
            "ETag": '"fake-etag"',
        }
        response.update(self.responses.get((Bucket, Key), {}))

        return response

    def get_object(
        self,
        Bucket: str,
        Key: str,
        Range: str | None = None,
    ) -> dict[str, Any]:
        body, _ = self.objects[(Bucket, Key)]

        if Range is None:
            return {"Body": FakeBody(body)}

        start, end = range_bounds(Range, len(body))

        return {"Body": FakeBody(body[start : end + 1])}


class FakeBody:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def read(self, size: int) -> bytes:
        chunk = self.data[self.offset : self.offset + size]
        self.offset += len(chunk)

        return chunk

    def close(self) -> None:
        return None


def range_bounds(header: str, size: int) -> tuple[int, int]:
    _, value = header.split("=", 1)
    start_text, end_text = value.split("-", 1)

    if not start_text:
        suffix_length = int(end_text)

        return max(0, size - suffix_length), size - 1

    start = int(start_text)
    end = int(end_text) if end_text else size - 1

    return start, min(end, size - 1)
