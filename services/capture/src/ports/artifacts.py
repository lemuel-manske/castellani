from abc import ABC, abstractmethod
from pathlib import Path

from domain.capture import ArtifactReference, WACZObject


class DecisionArtifacts(ABC):
    @abstractmethod
    async def delete_archive_objects(self, archive_id: str) -> int: ...


class ManifestArtifacts(ABC):
    @abstractmethod
    async def persist_manifest(self, archive_id: str, body: bytes) -> ArtifactReference: ...


class PackageArtifacts(ABC):
    @abstractmethod
    async def read_object(
        self,
        bucket: str,
        key: str,
    ) -> tuple[bytes, ArtifactReference]: ...

    @abstractmethod
    async def download_artifact(
        self,
        reference: ArtifactReference,
        destination: Path,
    ) -> Path: ...

    @abstractmethod
    async def persist_package(
        self,
        path: Path,
        archive_id: str,
        manifest_digest: str,
    ) -> ArtifactReference: ...


class WACZArtifacts(ABC):
    @abstractmethod
    async def read_wacz(
        self,
        reference: ArtifactReference,
        range_header: str | None,
        if_range: str | None,
        metadata_only: bool = False,
    ) -> WACZObject: ...
