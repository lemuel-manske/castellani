from pathlib import Path
from urllib.parse import quote

from domain.capture import TaskClaim

STAGING_PREFIX = "capture-staging"

PACKAGE_PREFIX = "packages"


def staging_artifact_key(claim: TaskClaim, snapshot_id: str, relative: Path) -> str:
    return "/".join(
        (
            STAGING_PREFIX,
            quote(claim.task.archive_id, safe=""),
            quote(claim.task.url_key, safe=""),
            quote(claim.attempt_id, safe=""),
            quote(snapshot_id, safe=""),
            *(quote(part, safe="") for part in relative.parts),
        )
    )


def package_key(archive_id: str, manifest_digest: str, package_digest: str) -> str:
    return f"{PACKAGE_PREFIX}/{quote(archive_id, safe='')}/{manifest_digest}/{package_digest}.wacz"


def archive_prefixes(archive_id: str) -> tuple[str, str]:
    quoted = quote(archive_id, safe="")

    return f"{STAGING_PREFIX}/{quoted}/", f"{PACKAGE_PREFIX}/{quoted}/"


__all__ = [
    "archive_prefixes",
    "package_key",
    "staging_artifact_key",
]
