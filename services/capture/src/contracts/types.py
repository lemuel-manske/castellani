from typing import TypedDict


class ArtifactReferenceContract(TypedDict):
    bucket: str
    key: str
    sha256: str
    sizeBytes: int
