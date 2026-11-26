from dataclasses import dataclass
from typing import Any

DEFAULT_AUTH_GENERATION = 0


class AuthGenerationChanged(RuntimeError):
    """Raised when an archive's authentication generation changed during a worker attempt."""


@dataclass(frozen=True)
class AuthContext:
    """An isolated, immutable authentication context for one capture attempt."""

    generation: int

    storage_state: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.generation < 0:
            raise ValueError("auth generation must not be negative")
