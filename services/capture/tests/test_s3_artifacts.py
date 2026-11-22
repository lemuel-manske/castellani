from pathlib import Path

import pytest

from adapters.artifacts.s3 import S3ArtifactStore
from support.domain import make_claim
from support.s3 import FakeS3


@pytest.mark.asyncio
async def test_s3_artifact_store_uploads_immutable_attempt_scoped_objects(
    tmp_path: Path,
    s3: FakeS3,
) -> None:
    store = S3ArtifactStore(s3, "private-artifacts", tmp_path)

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
    assert s3.objects[("private-artifacts", reference.key)][0] == b"warc-content"


@pytest.mark.asyncio
async def test_s3_artifact_store_rejects_files_outside_attempt_directory(
    tmp_path: Path,
    s3: FakeS3,
) -> None:
    store = S3ArtifactStore(s3, "private-artifacts", tmp_path)

    claim = make_claim()

    directory = await store.create_attempt_directory(claim)

    outside = tmp_path / "outside.warc.gz"
    outside.write_bytes(b"not attempt-owned")

    with pytest.raises(ValueError):
        await store.persist_attempt(claim, directory, "snapshot-1", (outside,))
