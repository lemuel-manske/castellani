from abc import ABC, abstractmethod
from pathlib import Path

from domain.capture import ArtifactReference


class DecisionArtifacts(ABC):
    @abstractmethod
    async def delete_archive_objects(self, archive_id: str) -> int: ...


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

