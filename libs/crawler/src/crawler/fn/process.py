import asyncio
import signal
import socket
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")

HOST = "127.0.0.1"

PROCESS_SHUTDOWN_TIMEOUT_SECONDS = 10


def available_port() -> int:
    """
    Returns an available port on the local machine.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((HOST, 0))

        return int(listener.getsockname()[1])


async def wait_for_process(process: asyncio.subprocess.Process) -> int:
    """
    Waits for a process to exit, ensuring that it is given a chance to complete
    before a cancellation is propagated.
    """

    try:
        return await process.wait()
    except asyncio.CancelledError:
        await stop_process(process)
        raise


async def stop_process(process: asyncio.subprocess.Process) -> None:
    """
    Stops a process, ensuring that it is given a chance to complete
    before a cancellation is propagated.
    """

    async def do_stop(process: asyncio.subprocess.Process) -> None:
        try:
            process.send_signal(signal.SIGINT)
        except ProcessLookupError:
            await process.wait()
            return

        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=PROCESS_SHUTDOWN_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            if process.returncode is None:
                process.kill()

            await process.wait()

    if process.returncode is not None:
        return

    await complete_before_cancellation(do_stop(process))


async def complete_before_cancellation(awaitable: Awaitable[T]) -> T:
    """
    Ensures that an awaitable is given a chance to complete before a cancellation is propagated.
    """

    task = asyncio.ensure_future(awaitable)

    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await task
        except BaseException as cleanup_error:
            raise cancellation from cleanup_error

        raise


__all__ = [
    "available_port",
    "complete_before_cancellation",
    "stop_process",
    "wait_for_process",
]
