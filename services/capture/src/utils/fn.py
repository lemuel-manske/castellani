import asyncio
from collections.abc import Callable, Coroutine
from functools import partial
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def awaitable(func: Callable[P, T]) -> Callable[P, Coroutine[None, None, T]]:
    """
    Wraps a function in an awaitable callable.
    """

    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        return await asyncio.to_thread(partial(func, *args, **kwargs))

    return wrapper


def noop(*args: Any, **kwargs: Any) -> None:
    """A no-op error handler."""

    pass
