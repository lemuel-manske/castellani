import asyncio
import logging
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from adapters.serialization import artifact_references
from capture.wacz import create_wacz, validate_wacz
from domain.capture import PendingPackage, PreparedPackage
from ports.artifacts import PackageArtifacts
from ports.capture import ArchivePublicationRepository
from topology.buckets import ARCHIVE_MANIFESTS_BUCKET

logger = logging.getLogger(__name__)


class ArchivePackager:
    """Builds and commits a WACZ from each committed crawl manifest."""

    def __init__(
        self,
        repository: ArchivePublicationRepository,
        artifacts: PackageArtifacts,
        root: Path,
        lease_duration: float = 60.0,
        poll_interval: float = 0.5,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if lease_duration <= 0:
            raise ValueError("lease_duration must be positive")

        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")

        self.repository = repository
        self.artifacts = artifacts
        self.root = root
        self.lease_duration = lease_duration
        self.poll_interval = poll_interval
        self.clock = clock

    async def package_once(self) -> bool:
        pending = await self.repository.claim_package(self.lease_duration)

        if pending is None:
            return False

        try:
            await self._package(pending)
        except Exception:
            await self.repository.release_package(pending)
            raise

        return True

    async def run(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

        while True:
            try:
                packaged = await self.package_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("archive packaging cycle failed")
                packaged = False

            if not packaged:
                await asyncio.sleep(self.poll_interval)

    async def _package(self, pending: PendingPackage) -> None:
        body, manifest_reference = await self.artifacts.read_object(
            ARCHIVE_MANIFESTS_BUCKET,
            pending.manifest_key,
        )

        if manifest_reference.sha256 != pending.manifest_digest:
            raise RuntimeError(f"manifest digest mismatch for {pending.archive_id}")

        references = artifact_references(body, pending.archive_id)

        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            root = Path(directory)
            war_files = [
                await self.artifacts.download_artifact(
                    reference,
                    root / f"warc-{index}.warc.gz",
                )
                for index, reference in enumerate(references)
            ]

            package_path = root / "package.wacz"

            create_wacz(war_files, package_path)
            validate_wacz(package_path, [path.name for path in war_files])

            artifact = await self.artifacts.persist_package(
                package_path,
                pending.archive_id,
                pending.manifest_digest,
            )

        await self.repository.prepare(
            PreparedPackage(
                archive_id=pending.archive_id,
                artifact=artifact,
                manifest_digest=pending.manifest_digest,
                occurred_at=datetime.fromtimestamp(self.clock(), UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                lease_owner=pending.lease_owner,
            )
        )
