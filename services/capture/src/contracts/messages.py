from typing import Final, NotRequired, TypedDict

from contracts.envelope import Envelope
from contracts.types import ArtifactReferenceContract

ARCHIVE_COMPENSATED_EVENT: Final = "ArchiveCompensated"
ARCHIVE_COMPENSATION_DECIDED_EVENT: Final = "ArchiveCompensationDecided"
ARCHIVE_PREPARED_EVENT: Final = "ArchivePrepared"
ARCHIVE_PUBLICATION_DECIDED_EVENT: Final = "ArchivePublicationDecided"
ARCHIVE_PUBLISHED_EVENT: Final = "ArchivePublished"
CAPTURE_PAGE_EVENT: Final = "CapturePage"
CRAWL_COMPLETED_EVENT: Final = "CrawlCompleted"
PAGE_CAPTURED_EVENT: Final = "PageCaptured"
START_CRAWL_EVENT: Final = "StartCrawl"


class CapturePagePayload(TypedDict):
    archiveId: str
    urlKey: str
    taskId: NotRequired[str]


class StartCrawlPayload(TypedDict):
    archiveId: str
    seedUrl: str
    maxDepth: int
    maxPages: int
    collectionId: NotRequired[str]
    allowedOrigins: NotRequired[list[str]]
    authGeneration: NotRequired[int]
    normalizerVersion: NotRequired[str]


class ArchivePublicationDecidedPayload(TypedDict):
    archiveId: str
    decisionVersion: int
    packageDigest: str


class ArchiveCompensationDecidedPayload(TypedDict):
    archiveId: str
    decisionVersion: int
    reasonCode: str


class PageCapturedPayload(TypedDict):
    archiveId: str
    snapshotId: str
    urlKey: str
    url: str
    capturedAt: str
    warcArtifacts: list[ArtifactReferenceContract]
    finalUrl: NotRequired[str]
    redirectChain: NotRequired[list[str]]
    contentType: NotRequired[str]


class CrawlCompletedPayload(TypedDict):
    archiveId: str
    manifest: ArtifactReferenceContract
    manifestDigest: str
    seedSucceeded: bool
    capturedCount: int
    failedCount: int


class ArchivePreparedPayload(TypedDict):
    archiveId: str
    package: ArtifactReferenceContract
    packageDigest: str
    manifestDigest: str


class ArchivePublishedPayload(TypedDict):
    archiveId: str
    decisionVersion: int
    packageDigest: str


class ArchiveCompensatedPayload(TypedDict):
    archiveId: str
    decisionVersion: int


CapturePageEnvelope = Envelope[CapturePagePayload]
StartCrawlEnvelope = Envelope[StartCrawlPayload]
ArchivePublicationDecidedEnvelope = Envelope[ArchivePublicationDecidedPayload]
ArchiveCompensationDecidedEnvelope = Envelope[ArchiveCompensationDecidedPayload]
PageCapturedEnvelope = Envelope[PageCapturedPayload]
CrawlCompletedEnvelope = Envelope[CrawlCompletedPayload]
ArchivePreparedEnvelope = Envelope[ArchivePreparedPayload]
ArchivePublishedEnvelope = Envelope[ArchivePublishedPayload]
ArchiveCompensatedEnvelope = Envelope[ArchiveCompensatedPayload]
