from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

NAVIGATION_TIMEOUT_MILLISECONDS = 30_000
NETWORK_IDLE_TIMEOUT_MILLISECONDS = 5_000

DEFAULT_MAX_REQUESTS = 500
DEFAULT_MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_DISCOVERED_LINKS = 1_000
DEFAULT_ALLOW_PRIVATE_NETWORKS = False


@dataclass(frozen=True)
class CaptureLimits:
    navigation_timeout_milliseconds: int = NAVIGATION_TIMEOUT_MILLISECONDS
    network_idle_timeout_milliseconds: int = NETWORK_IDLE_TIMEOUT_MILLISECONDS
    max_requests: int = DEFAULT_MAX_REQUESTS
    max_document_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES
    max_discovered_links: int = DEFAULT_MAX_DISCOVERED_LINKS
    allow_private_networks: bool = DEFAULT_ALLOW_PRIVATE_NETWORKS


@dataclass(frozen=True)
class BrowserCaptureResult:
    requested_url: str
    final_url: str
    redirect_chain: tuple[str, ...]
    status_code: int | None
    content_type: str | None
    title: str
    captured_at: datetime
    discovered_urls: tuple[str, ...]
    blocked_urls: tuple[str, ...]
    warc_files: tuple[Path, ...]


class CaptureFailureCode(StrEnum):
    INVALID_URL = "invalid_url"
    UNSAFE_REQUEST = "unsafe_request"
    REQUEST_LIMIT_EXCEEDED = "request_limit_exceeded"
    DOCUMENT_LIMIT_EXCEEDED = "document_limit_exceeded"
    DISCOVERED_LINK_LIMIT_EXCEEDED = "discovered_link_limit_exceeded"
    NAVIGATION_FAILED = "navigation_failed"
    DOWNLOAD_FAILED = "download_failed"
    RECORDING_FAILED = "recording_failed"


class CaptureFailure(RuntimeError):
    def __init__(self, reason_code: CaptureFailureCode, message: str) -> None:
        super().__init__(message)

        self.reason_code = reason_code


class InvalidCaptureURL(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.INVALID_URL, message)


class UnsafeCaptureRequest(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.UNSAFE_REQUEST, message)


class RequestLimitExceeded(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.REQUEST_LIMIT_EXCEEDED, message)


class DocumentLimitExceeded(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.DOCUMENT_LIMIT_EXCEEDED, message)


class DiscoveredLinkLimitExceeded(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.DISCOVERED_LINK_LIMIT_EXCEEDED, message)


class CaptureNavigationFailed(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.NAVIGATION_FAILED, message)


class CaptureDownloadFailed(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.DOWNLOAD_FAILED, message)


class CaptureRecordingFailed(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.RECORDING_FAILED, message)


__all__ = [
    "BrowserCaptureResult",
    "CaptureDownloadFailed",
    "CaptureLimits",
    "CaptureNavigationFailed",
    "CaptureRecordingFailed",
    "DiscoveredLinkLimitExceeded",
    "DocumentLimitExceeded",
    "InvalidCaptureURL",
    "RequestLimitExceeded",
    "UnsafeCaptureRequest",
]
