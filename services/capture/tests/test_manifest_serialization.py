import json

import pytest

from adapters.serialization import artifact_references
from domain.capture import ArtifactReference


def test_artifact_references_reads_authorized_warcs() -> None:
    manifest: dict[str, object] = {
        "archiveId": "archive-1",
        "snapshots": [
            {
                "warcArtifacts": [
                    {
                        "bucket": "capture-artifacts",
                        "key": "capture-staging/archive-1/attempt-1/capture.warc.gz",
                        "sha256": "a" * 64,
                        "sizeBytes": 128,
                        "versionId": "version-1",
                    }
                ]
            }
        ],
    }

    assert artifact_references(json.dumps(manifest).encode(), "archive-1") == (
        ArtifactReference(
            bucket="capture-artifacts",
            key="capture-staging/archive-1/attempt-1/capture.warc.gz",
            sha256="a" * 64,
            size_bytes=128,
            version_id="version-1",
        ),
    )


def test_artifact_references_rejects_foreign_manifest() -> None:
    manifest: dict[str, object] = {"archiveId": "archive-1", "snapshots": []}

    with pytest.raises(ValueError, match="manifest archive mismatch"):
        artifact_references(json.dumps(manifest).encode(), "archive-2")
