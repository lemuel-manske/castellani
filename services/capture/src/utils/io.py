import asyncio
from collections.abc import AsyncIterator
from typing import Any

STREAM_CHUNK_BYTES = 64 * 1024


async def collect(body: AsyncIterator[bytes] | None) -> bytes:
    """Collects an async byte stream into bytes."""

    assert body is not None

    return b"".join([chunk async for chunk in body])


async def stream_body(body: Any) -> AsyncIterator[bytes]:
    """
    Streams the contents of a file-like object in chunks of bytes.
    """

    try:
        while chunk := await asyncio.to_thread(body.read, STREAM_CHUNK_BYTES):
            yield chunk
    finally:
        await asyncio.to_thread(body.close)
