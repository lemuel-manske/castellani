from pathlib import Path
from typing import Any

import pytest

from adapters.artifacts.s3 import S3ArtifactStore
from domain import PageTask, TaskClaim


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, dict[str, str]]] = {}

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        ExtraArgs: dict[str, Any],
    ) -> None:
        self.objects[(bucket, key)] = (
            Path(filename).read_bytes(),
            ExtraArgs["Metadata"],
        )

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        body, metadata = self.objects[(Bucket, Key)]
        return {
            "ContentLength": len(body),
            "Metadata": metadata,
            "VersionId": "version-1",
        }


def make_claim() -> TaskClaim:
    return TaskClaim(
        task=PageTask("archive/one", "url-key", "https://example.org/", 0),
        attempt_id="attempt-1",
        fence=1,
        lease_until=100,
    )


@pytest.mark.asyncio
async def test_s3_artifact_store_uploads_immutable_attempt_scoped_objects(
    tmp_path: Path,
) -> None:
    client = FakeS3()
    store = S3ArtifactStore(client, "private-artifacts", tmp_path)
    claim = make_claim()
    directory = await store.create_attempt_directory(claim)
    warc = directory / "records" / "capture.warc.gz"
    warc.parent.mkdir()
    warc.write_bytes(b"warc-content")

    references = await store.persist_attempt(
        claim,
        directory,
        "snapshot-1",
        (warc,),
    )

    assert len(references) == 1
    reference = references[0]
    assert reference.bucket == "private-artifacts"
    assert reference.key.startswith("capture-staging/archive%2Fone/url-key/attempt-1/")
    assert reference.key.endswith("records/capture.warc.gz")
    assert reference.sha256
    assert reference.size_bytes == len(b"warc-content")
    assert reference.version_id == "version-1"
    assert client.objects[("private-artifacts", reference.key)][0] == b"warc-content"


@pytest.mark.asyncio
async def test_s3_artifact_store_rejects_files_outside_attempt_directory(
    tmp_path: Path,
) -> None:
    store = S3ArtifactStore(FakeS3(), "private-artifacts", tmp_path)
    claim = make_claim()
    directory = await store.create_attempt_directory(claim)
    outside = tmp_path / "outside.warc.gz"
    outside.write_bytes(b"not attempt-owned")

    with pytest.raises(ValueError):
        await store.persist_attempt(claim, directory, "snapshot-1", (outside,))
