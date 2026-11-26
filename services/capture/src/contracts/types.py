from typing import NotRequired, TypedDict


class ArtifactReferenceContract(TypedDict):
    bucket: str
    key: str
    sha256: str
    sizeBytes: int
    versionId: NotRequired[str]
