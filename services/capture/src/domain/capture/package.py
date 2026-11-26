from dataclasses import dataclass
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

from .capture import ArtifactReference

PACKAGE_PENDING = "PENDING"
PACKAGE_PREPARING = "PREPARING"
PACKAGE_PREPARED = "PREPARED"

DECISION_PUBLISH = "PUBLISH"
DECISION_COMPENSATE = "COMPENSATE"

REPLAY_READY = "READY"


@dataclass(frozen=True)
class PendingPackage:
    """A committed crawl manifest awaiting WACZ packaging."""

    archive_id: str
    manifest_key: str
    manifest_digest: str
    closed_at: str
    lease_owner: str


@dataclass(frozen=True)
class PreparedPackage:
    """The immutable package that satisfies a pending crawl."""

    archive_id: str
    artifact: ArtifactReference
    manifest_digest: str
    occurred_at: str
    lease_owner: str


@dataclass(frozen=True)
class PublicationDecision:
    """A durable Coordinator decision to expose a prepared package."""

    archive_id: str
    correlation_id: str
    decision_version: int
    package_digest: str
    occurred_at: str


@dataclass(frozen=True)
class CompensationDecision:
    """A durable Coordinator decision to abort and clean up a run."""

    archive_id: str
    correlation_id: str
    decision_version: int
    reason_code: str
    occurred_at: str


class InvalidArchiveDecision(ValueError):
    """Raised when a decision conflicts with local durable facts."""


class PackageCommitRejected(RuntimeError):
    """Raised when a package cannot be committed to its run."""


def package_key(archive_id: str, manifest_digest: str, package_digest: str) -> str:
    return f"packages/{quote(archive_id, safe='')}/{manifest_digest}/{package_digest}.wacz"


def archive_prepared_message_id(archive_id: str, manifest_digest: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"archive-prepared:{archive_id}:{manifest_digest}"))


def archive_published_message_id(archive_id: str, decision_version: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"archive-published:{archive_id}:{decision_version}"))


def archive_compensated_message_id(archive_id: str, decision_version: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"archive-compensated:{archive_id}:{decision_version}"))
