import asyncio
from collections.abc import Callable

import httpx

STARTUP_TIMEOUT_SECONDS = 15


async def wait_for_http_response(
    process: asyncio.subprocess.Process,
    url: str,
    is_ready: Callable[[httpx.Response], bool],
) -> httpx.Response:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + STARTUP_TIMEOUT_SECONDS
    last_response: httpx.Response | None = None
    last_error: httpx.TransportError | None = None

    async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
        while loop.time() < deadline:
            if process.returncode is not None:
                raise RuntimeError(
                    f"pywb process exited before becoming ready (exit code {process.returncode})"
                )

            try:
                response = await client.get(url)
            except httpx.TransportError as error:
                last_error = error
            else:
                last_response = response

                if is_ready(response):
                    return response

            remaining = deadline - loop.time()

            if remaining > 0:
                await asyncio.sleep(min(0.1, remaining))

    if last_response is not None:
        raise TimeoutError(
            f"pywb did not become ready at {url}; "
            f"last response was HTTP {last_response.status_code}"
        )

    if last_error is not None:
        raise TimeoutError(
            f"pywb did not become ready at {url}; last connection error was {last_error}"
        ) from last_error

    raise TimeoutError(f"pywb did not become ready at {url}")


__all__ = [
    "wait_for_http_response",
]
