# libs/crawler

Browser page capture, WARC recording, and WACZ packaging primitives for Castellani. The Capture service consumes this library for page execution, recording, replay, and WACZ packaging.

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

WACZ packaging and validation are available from the narrower `crawler.wacz` module:

```python
from crawler.wacz import create_wacz, validate_wacz
```
