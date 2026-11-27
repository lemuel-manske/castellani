from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from domain.capture import (
    DECISION_PUBLISH,
    REPLAY_READY,
    ArtifactReference,
    InvalidPageLimit,
    PageListing,
    SnapshotReference,
)
from ports.capture import ArchiveCatalog

from .queries.archive import MAX_PAGE_LIMIT, query_pages
from .queries.archive import read_snapshot as read_snapshot_query
from .queries.task import read_run
from .values import optional_number, optional_string

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient


class DynamoDBArchiveCatalog(ArchiveCatalog):
    """Reads archive metadata and the reference to its published package."""

    def __init__(self, client: DynamoDBClient) -> None:
        self.client = client

    async def list_pages(
        self,
        archive_id: str,
        limit: int,
        cursor: str | None,
    ) -> PageListing:
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise InvalidPageLimit("limit must be between 1 and 100")

        def read() -> PageListing:
            return query_pages(self.client, archive_id, limit, cursor)

        return await asyncio.to_thread(read)

    async def read_snapshot(
        self,
        archive_id: str,
        snapshot_id: str,
    ) -> SnapshotReference | None:
        def read() -> SnapshotReference | None:
            return read_snapshot_query(self.client, archive_id, snapshot_id)

        return await asyncio.to_thread(read)

    async def read_package(self, archive_id: str) -> ArtifactReference | None:
        def read() -> ArtifactReference | None:
            run = read_run(self.client, archive_id)

            if run is None or (optional_string(run, "decision") or "") != DECISION_PUBLISH:
                return None

            if (optional_string(run, "replayStatus") or "") != REPLAY_READY:
                return None

            bucket = optional_string(run, "packageBucket")
            key = optional_string(run, "packageKey")
            digest = optional_string(run, "packageDigest")
            size_bytes = optional_number(run, "packageSizeBytes")

            if not bucket or not key or not digest or size_bytes is None:
                return None

            return ArtifactReference(
                bucket=bucket,
                key=key,
                sha256=digest,
                size_bytes=int(size_bytes),
            )

        return await asyncio.to_thread(read)
