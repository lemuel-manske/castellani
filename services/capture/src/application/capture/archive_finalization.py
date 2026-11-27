import json

from adapters.serialization import manifest_document
from domain.capture import ManifestFinalization, ManifestSource
from ports.artifacts import ManifestArtifacts
from ports.capture import ArchiveFinalizationRepository, CrawlFinalizer


def serialize_manifest(source: ManifestSource) -> bytes:
    document = manifest_document(source)

    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


class ArchiveManifestFinalizer(CrawlFinalizer):
    """Writes the immutable crawl manifest and commits its finalization."""

    def __init__(
        self,
        repository: ArchiveFinalizationRepository,
        artifacts: ManifestArtifacts,
    ) -> None:
        self.repository = repository
        self.artifacts = artifacts

    async def __call__(self, archive_id: str) -> None:
        source = await self.repository.read_manifest_source(archive_id)

        if source is None:
            return

        artifact = await self.artifacts.persist_manifest(
            archive_id,
            serialize_manifest(source),
        )

        await self.repository.commit_manifest(
            ManifestFinalization(
                archive_id=archive_id,
                artifact=artifact,
                digest=artifact.sha256,
                occurred_at=source.run.closed_at,
                seed_succeeded=source.seed_succeeded,
                captured_count=len(source.snapshots),
                failed_count=len(source.failures),
            )
        )
