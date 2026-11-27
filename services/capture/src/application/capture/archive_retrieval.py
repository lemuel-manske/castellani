from domain.capture import PageListing, SnapshotReference, WACZObject
from ports.artifacts import WACZArtifacts
from ports.capture import ArchiveCatalog


class ArchiveRetrieval:
    """Serves archive pages and published WACZ objects from durable sources."""

    def __init__(
        self,
        catalog: ArchiveCatalog,
        artifacts: WACZArtifacts,
    ) -> None:
        self.catalog = catalog
        self.artifacts = artifacts

    async def list_pages(
        self,
        archive_id: str,
        limit: int,
        cursor: str | None,
    ) -> PageListing:
        return await self.catalog.list_pages(archive_id, limit, cursor)

    async def read_snapshot(
        self,
        archive_id: str,
        snapshot_id: str,
    ) -> SnapshotReference | None:
        return await self.catalog.read_snapshot(archive_id, snapshot_id)

    async def read_wacz(
        self,
        archive_id: str,
        range_header: str | None,
        if_range: str | None,
        metadata_only: bool = False,
    ) -> WACZObject | None:
        reference = await self.catalog.read_package(archive_id)

        if reference is None:
            return None

        return await self.artifacts.read_wacz(
            reference,
            range_header,
            if_range,
            metadata_only,
        )
