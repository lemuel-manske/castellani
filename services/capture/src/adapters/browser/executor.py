from pathlib import Path

from capture.browser import CaptureLimits, capture_page
from capture.worker import CaptureArtifact
from capture.worker.api import CaptureExecutor
from domain.capture import PageCapture


class BrowserPageExecutor(CaptureExecutor):
    """Adapts the browser capture engine to the worker's page-execution port."""

    def __init__(self, limits: CaptureLimits | None = None) -> None:
        self.limits = limits or CaptureLimits()

    async def execute(self, url: str, output_dir: Path) -> CaptureArtifact:
        result = await capture_page(url, output_dir, limits=self.limits)

        return CaptureArtifact(
            capture=PageCapture(
                requested_url=result.requested_url,
                final_url=result.final_url,
                redirect_chain=result.redirect_chain,
                status_code=result.status_code,
                content_type=result.content_type,
                title=result.title,
                captured_at=result.captured_at,
                discovered_urls=result.discovered_urls,
            ),
            blocked_urls=result.blocked_urls,
            warc_files=result.warc_files,
        )
