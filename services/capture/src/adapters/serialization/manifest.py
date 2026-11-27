import json
from typing import Any, cast

from contracts.types import ArtifactReferenceContract
from domain.capture import (
    DEFAULT_NORMALIZER_VERSION,
    MANIFEST_SCHEMA_VERSION,
    ArtifactReference,
    ManifestSnapshot,
    ManifestSource,
)


def manifest_document(source: ManifestSource) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "archiveId": source.run.archive_id,
        "normalizerVersion": source.run.normalizer_version or DEFAULT_NORMALIZER_VERSION,
        "seedUrl": source.run.seed_url,
        "createdAt": source.run.closed_at,
        "snapshots": [snapshot_entry(item) for item in source.snapshots],
        "failedPages": [
            {"urlKey": item.url_key, "reasonCode": item.reason_code} for item in source.failures
        ],
    }

    if source.run.collection_id is not None:
        document["collectionId"] = source.run.collection_id

    return document


def snapshot_entry(item: ManifestSnapshot) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "snapshotId": item.snapshot_id,
        "urlKey": item.url_key,
        "url": item.url,
        "finalUrl": item.final_url,
        "capturedAt": item.captured_at,
        "warcArtifacts": [artifact_document(reference) for reference in item.warc_artifacts],
    }

    if item.redirect_chain is not None:
        entry["redirectChain"] = list(item.redirect_chain)

    if item.min_depth is not None:
        entry["minDepth"] = item.min_depth

    if item.content_type is not None:
        entry["contentType"] = item.content_type

    return entry


def artifact_reference(raw: ArtifactReferenceContract) -> ArtifactReference:
    return ArtifactReference(
        bucket=str(raw["bucket"]),
        key=str(raw["key"]),
        sha256=str(raw["sha256"]),
        size_bytes=int(raw["sizeBytes"]),
    )


def artifact_document(reference: ArtifactReference) -> ArtifactReferenceContract:
    document: ArtifactReferenceContract = {
        "bucket": reference.bucket,
        "key": reference.key,
        "sha256": reference.sha256,
        "sizeBytes": reference.size_bytes,
    }

    return document


def artifact_references(body: bytes, archive_id: str) -> tuple[ArtifactReference, ...]:
    decoded: object = json.loads(body)

    if not isinstance(decoded, dict):
        raise ValueError("manifest is not an object")

    manifest = cast(dict[str, Any], decoded)

    if manifest.get("archiveId") != archive_id:
        raise ValueError(f"manifest archive mismatch for {archive_id}")

    snapshots = manifest.get("snapshots")

    if not isinstance(snapshots, list) or not snapshots:
        raise ValueError("manifest has no authorized snapshots")

    references: list[ArtifactReference] = []

    for raw_snapshot in cast(list[Any], snapshots):
        if not isinstance(raw_snapshot, dict):
            raise ValueError("manifest contains an invalid snapshot")

        snapshot = cast(dict[str, Any], raw_snapshot)
        artifacts = snapshot.get("warcArtifacts")

        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("manifest snapshot has no WARC artifacts")

        for raw_artifact in cast(list[Any], artifacts):
            if not isinstance(raw_artifact, dict):
                raise ValueError("manifest contains an invalid artifact reference")

            artifact = cast(ArtifactReferenceContract, raw_artifact)

            references.append(artifact_reference(artifact))

    if not references:
        raise ValueError("manifest has no WARC artifacts")

    return tuple(references)
