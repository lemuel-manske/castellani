import asyncio
import sys

import pytest

from capture.browser.recording import stop_process, wait_for_process


async def start_long_running_process(
    *arguments: str,
    wait_for_ready: bool = False,
) -> asyncio.subprocess.Process:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        *arguments,
        stdout=asyncio.subprocess.PIPE if wait_for_ready else asyncio.subprocess.DEVNULL,
    )

    if wait_for_ready:
        if process.stdout is None:
            raise RuntimeError("process stdout was not captured")

        await process.stdout.readline()

    return process


@pytest.mark.asyncio
async def test_stop_process_waits_until_child_exits() -> None:
    process = await start_long_running_process("import time; time.sleep(60)")

    await stop_process(process)

    assert process.returncode is not None


@pytest.mark.asyncio
async def test_stop_process_kills_child_that_ignores_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("capture.browser.recording.PROCESS_SHUTDOWN_TIMEOUT_SECONDS", 0.01)
    process = await start_long_running_process(
        "import signal, time; signal.signal(signal.SIGINT, signal.SIG_IGN); "
        "print('ready', flush=True); time.sleep(60)",
        wait_for_ready=True,
    )

    await stop_process(process)

    assert process.returncode is not None


@pytest.mark.asyncio
async def test_cancellation_waits_for_process_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("capture.browser.recording.PROCESS_SHUTDOWN_TIMEOUT_SECONDS", 0.05)
    process = await start_long_running_process(
        "import signal, time; signal.signal(signal.SIGINT, signal.SIG_IGN); "
        "print('ready', flush=True); time.sleep(60)",
        wait_for_ready=True,
    )
    shutdown = asyncio.create_task(stop_process(process))

    await asyncio.sleep(0.01)
    shutdown.cancel()

    with pytest.raises(asyncio.CancelledError):
        await shutdown

    assert process.returncode is not None


@pytest.mark.asyncio
async def test_cancelling_process_wait_stops_child() -> None:
    process = await start_long_running_process("import time; time.sleep(60)")
    waiting = asyncio.create_task(wait_for_process(process))

    await asyncio.sleep(0.01)
    waiting.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiting

    assert process.returncode is not None
