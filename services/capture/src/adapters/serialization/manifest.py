import json
from typing import Any, cast

from contracts.types import ArtifactReferenceContract
from domain.capture import (
    DEFAULT_NORMALIZER_VERSION,
    MANIFEST_SCHEMA_VERSION,
    ArtifactReference,
)


def manifest_document(
    run: dict[str, Any],
    snapshots: list[dict[str, Any]],
    frontier: list[dict[str, Any]],
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "archiveId": run["archiveId"],
        "normalizerVersion": run.get("normalizerVersion") or DEFAULT_NORMALIZER_VERSION,
        "seedUrl": run["seedUrl"],
        "createdAt": run["closedAt"],
        "snapshots": [snapshot_entry(item) for item in snapshots],
        "failedPages": [
            {
                "urlKey": item["urlKey"],
                "reasonCode": item.get("failureReason") or "capture_failed",
            }
            for item in frontier
            if item.get("state") == "FAILED"
        ],
    }

    collection_id = run.get("collectionId")

    if collection_id is not None:
        document["collectionId"] = collection_id

    return document


def snapshot_entry(item: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "snapshotId": item["snapshotId"],
        "urlKey": item["urlKey"],
        "url": item["url"],
        "finalUrl": item["finalUrl"],
        "capturedAt": item["capturedAt"],
        "warcArtifacts": [
            artifact_document(artifact_reference(ref)) for ref in item["warcArtifacts"]
        ],
    }

    if "redirectChain" in item:
        entry["redirectChain"] = item["redirectChain"]

    if "minDepth" in item:
        entry["minDepth"] = item["minDepth"]

    if "contentType" in item:
        entry["contentType"] = item["contentType"]

    return entry


def artifact_reference(raw: ArtifactReferenceContract) -> ArtifactReference:
    version = raw.get("versionId")

    return ArtifactReference(
        bucket=str(raw["bucket"]),
        key=str(raw["key"]),
        sha256=str(raw["sha256"]),
        size_bytes=int(raw["sizeBytes"]),
        version_id=None if version is None else str(version),
    )


def artifact_document(reference: ArtifactReference) -> ArtifactReferenceContract:
    document: ArtifactReferenceContract = {
        "bucket": reference.bucket,
        "key": reference.key,
        "sha256": reference.sha256,
        "sizeBytes": reference.size_bytes,
    }

    if reference.version_id is not None:
        document["versionId"] = reference.version_id

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
