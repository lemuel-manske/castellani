import gzip
from collections.abc import Sequence
from pathlib import Path


def read_gzip_files(files: Sequence[Path]) -> bytes:
    content = b""

    for f in files:
        with gzip.open(f, "rb") as gz:
            content += gz.read()

    return content
