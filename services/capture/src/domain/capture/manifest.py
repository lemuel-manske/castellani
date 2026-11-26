from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

from .url_identity import URL_IDENTITY_VERSION

MANIFEST_SCHEMA_VERSION = 1
DEFAULT_NORMALIZER_VERSION = f"v{URL_IDENTITY_VERSION}"


def is_supported_normalizer_version(version: str | None) -> bool:
    return version is None or version == DEFAULT_NORMALIZER_VERSION


def manifest_key(archive_id: str, digest: str) -> str:
    return f"manifests/{quote(archive_id, safe='')}/{digest}.json"


def manifest_message_id(archive_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"crawl-completed:{archive_id}"))
