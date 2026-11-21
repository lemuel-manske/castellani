from typing import Protocol

from .browser_reservation import BrowserReservation


class BrowserCapacity(Protocol):
    """Controls the number of page captures running concurrently."""

    async def reserve(self, attempt_id: str) -> BrowserReservation | None: ...

    async def renew(self, reservation: BrowserReservation) -> BrowserReservation: ...

    async def release(self, reservation: BrowserReservation) -> None: ...
