from typing import Protocol


class Clock(Protocol):
    """Returns the current Unix timestamp in seconds."""

    def __call__(self) -> float: ...
