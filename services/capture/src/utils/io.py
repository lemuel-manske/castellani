import asyncio
import gzip
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

STREAM_CHUNK_BYTES = 64 * 1024


async def collect(body: AsyncIterator[bytes] | None) -> bytes:
    """Collects an async byte stream into bytes."""

    assert body is not None

    return b"".join([chunk async for chunk in body])


def read_gzip_files(files: Sequence[Path]) -> bytes:
    """
    Reads the contents of multiple gzip-compressed files and returns the concatenated bytes.
    """

    content = b""

    for f in files:
        with gzip.open(f, "rb") as gz:
            content += gz.read()

    return content


async def stream_body(body: Any) -> AsyncIterator[bytes]:
    """
    Streams the contents of a file-like object in chunks of bytes.
    """

    try:
        while chunk := await asyncio.to_thread(body.read, STREAM_CHUNK_BYTES):
            yield chunk
    finally:
        await asyncio.to_thread(body.close)
