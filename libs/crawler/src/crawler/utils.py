import asyncio
import subprocess
from pathlib import Path


async def trust_certificate(certificate_path: Path, browser_home: Path) -> None:
    database_path = browser_home / ".pki" / "nssdb"
    database_path.mkdir(parents=True, exist_ok=True)

    database_uri = f"sql:{database_path}"

    await asyncio.to_thread(
        subprocess.run,
        ["certutil", "-N", "-d", database_uri, "--empty-password"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    await asyncio.to_thread(
        subprocess.run,
        [
            "certutil",
            "-A",
            "-d",
            database_uri,
            "-n",
            "Castellani Capture Recorder",
            "-t",
            "C,,",
            "-i",
            str(certificate_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


__all__ = [
    "trust_certificate",
]
