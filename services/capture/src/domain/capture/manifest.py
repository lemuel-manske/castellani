from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

MANIFEST_SCHEMA_VERSION = 1
DEFAULT_NORMALIZER_VERSION = "v1"


def manifest_key(archive_id: str) -> str:
    return f"manifests/{quote(archive_id, safe='')}/manifest.json"


def manifest_message_id(archive_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"crawl-completed:{archive_id}"))
