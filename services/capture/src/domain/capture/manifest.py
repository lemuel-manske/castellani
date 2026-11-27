from dataclasses import dataclass
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

from .capture import ArtifactReference
from .url_identity import URL_IDENTITY_VERSION

MANIFEST_SCHEMA_VERSION = 1
DEFAULT_NORMALIZER_VERSION = f"v{URL_IDENTITY_VERSION}"


@dataclass(frozen=True)
class ManifestRun:
    archive_id: str
    seed_url: str
    closed_at: str
    normalizer_version: str | None = None
    collection_id: str | None = None


@dataclass(frozen=True)
class ManifestSnapshot:
    snapshot_id: str
    url_key: str
    url: str
    final_url: str
    captured_at: str
    warc_artifacts: tuple[ArtifactReference, ...]
    redirect_chain: tuple[str, ...] | None = None
    min_depth: int | None = None
    content_type: str | None = None


@dataclass(frozen=True)
class ManifestFailure:
    url_key: str
    reason_code: str


@dataclass(frozen=True)
class ManifestSource:
    run: ManifestRun
    snapshots: tuple[ManifestSnapshot, ...]
    failures: tuple[ManifestFailure, ...]
    seed_succeeded: bool


@dataclass(frozen=True)
class ManifestFinalization:
    archive_id: str
    artifact: ArtifactReference
    digest: str
    occurred_at: str
    seed_succeeded: bool
    captured_count: int
    failed_count: int


def is_supported_normalizer_version(version: str | None) -> bool:
    return version is None or version == DEFAULT_NORMALIZER_VERSION


def manifest_key(archive_id: str, digest: str) -> str:
    return f"manifests/{quote(archive_id, safe='')}/{digest}.json"


def manifest_message_id(archive_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"crawl-completed:{archive_id}"))
