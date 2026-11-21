# Capture

Capture executes page-level web captures for Castellani. Its distributed frontier remains the authority for URL admission, task ownership, retries, and crawl completion; browser execution does not schedule work independently.

## Development

> [!NOTE]
> On Linux, `certutil` from `libnss3-tools` must be available so Chromium can trust the attempt-local recorder CA without disabling TLS verification. Each capture attempt owns its recorder process, browser profile, and output directory.

Install the pinned Python toolchain and dependencies with `make install`.

Install the matching Playwright browser with `uv run playwright install chromium`.

- `make install`: download dependencies.
- `make run`: start the Coordinator.
- `make fmt`: apply repository Go formatting conventions.
- `make test`: run all tests.
- `make check`: run static analysis and compile all packages without executing tests.

The local recording prototype uses pywb as an HTTP(S) recording proxy.
