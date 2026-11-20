# Capture

Capture executes page-level web captures for Castellani. Its distributed frontier remains the authority for URL admission, task ownership, retries, and crawl completion; browser execution does not schedule work independently.

## Development

Install the pinned Python toolchain and dependencies with `make install`. Install the matching Playwright browser with `uv run playwright install chromium`, then start the service with `make run`.

The local recording prototype uses pywb as an HTTP(S) recording proxy. On Linux, `certutil` from `libnss3-tools` must be available so Chromium can trust the attempt-local recorder CA without disabling TLS verification. Each capture attempt owns its recorder process, browser profile, and output directory.

Run `make test` for fast service tests, `make test-integration` for the local WARC recording and offline replay acceptance test, and `make check` for linting and type checking. Integration tests require the Playwright Chromium browser and `certutil`. The broader WARC fidelity acceptance gate is documented in [ADR-0026](../../docs/adr/0026-capture-local-warc-recording.md).
