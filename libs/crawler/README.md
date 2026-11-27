# libs/crawler

Browser page capture and WARC recording primitives for Castellani. This is a standalone copy of the crawler mechanism currently kept in `services/capture/src/capture/browser`; the Capture service has not switched over to it yet.

Each capture owns its recording proxy, Chromium profile, and output directory. Scheduling, queueing, and artifact persistence remain in the consuming service.

## Development

> [!NOTE]
> On Linux, `certutil` from `libnss3-tools` must be available so Chromium can trust the attempt-local recorder CA without disabling TLS verification. Integration tests also require the `wayback` and `wb-manager` executables installed by pywb.

Install the matching Playwright browser with `uv run playwright install chromium`.

- `make install`: download dependencies.
- `make fmt`: format and lint the Python library.
- `make test-unit`: run tests that do not need a browser or recorder.
- `make test-integration`: run tests exercising Chromium and pywb.
- `make test`: run both unit and integration tests.
- `make check`: run static analysis.

## Usage

```python
from pathlib import Path

from crawler import capture_page, is_valid_url

if is_valid_url("https://example.org/"):
    result = await capture_page("https://example.org/", Path("/tmp/castellani/crawler"))
```
