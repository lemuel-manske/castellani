from dataclasses import dataclass
from hashlib import sha256


def new_reservation_id(attempt_id: str) -> str:
    digest = sha256(attempt_id.encode("utf-8")).hexdigest()

    return f"browser-{digest}"


class InvalidReservationRenewal(ValueError):
    """Raised when a reservation renewal violates ownership or lease invariants."""


class CaptureReservationLostError(RuntimeError):
    """Raised when a reservation can no longer be renewed by its owner."""


@dataclass(frozen=True)
class CaptureReservation:
    """A fenced, time-limited reservation of one global browser-capacity slot."""

    attempt_id: str
    reservation_id: str
    slot_id: str
    fence: int
    lease_until: float

    def __post_init__(self) -> None:
        if not self.attempt_id:
            raise ValueError("attempt_id must not be empty")

        if not self.reservation_id:
            raise ValueError("reservation_id must not be empty")

        if not self.slot_id:
            raise ValueError("slot_id must not be empty")

        if self.fence < 1:
            raise ValueError("fence must be positive")

        if self.lease_until <= 0:
            raise ValueError("lease_until must be positive")

    def verify_renewal(self, renewed: "CaptureReservation", now: float) -> None:
        if (
            renewed.attempt_id != self.attempt_id
            or renewed.reservation_id != self.reservation_id
            or renewed.slot_id != self.slot_id
            or renewed.fence != self.fence
            or renewed.lease_until <= max(self.lease_until, now)
        ):
            raise InvalidReservationRenewal(
                "browser reservation renewal returned an invalid reservation"
            )
