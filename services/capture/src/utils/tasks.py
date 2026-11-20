import asyncio
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


async def complete_before_cancellation(awaitable: Awaitable[T]) -> T:
    task = asyncio.ensure_future(awaitable)

    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await task
        except BaseException as cleanup_error:
            raise cancellation from cleanup_error

        raise
