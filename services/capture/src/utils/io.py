import gzip
from collections.abc import AsyncIterator, Sequence
from pathlib import Path


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
