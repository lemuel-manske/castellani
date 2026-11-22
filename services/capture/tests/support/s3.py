from pathlib import Path
from typing import Any


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

    def list_object_versions(
        self,
        Bucket: str,
        Prefix: str,
        KeyMarker: str | None = None,
        VersionIdMarker: str | None = None,
    ) -> dict[str, Any]:
        del KeyMarker, VersionIdMarker
        versions = [
            {"Key": key, "VersionId": "version-1"}
            for bucket, key in self.objects
            if bucket == Bucket and key.startswith(Prefix)
        ]
        return {"Versions": versions, "DeleteMarkers": [], "IsTruncated": False}

    def delete_objects(self, Bucket: str, Delete: dict[str, Any]) -> dict[str, Any]:
        for item in Delete["Objects"]:
            self.objects.pop((Bucket, item["Key"]), None)
        return {"Deleted": Delete["Objects"]}
