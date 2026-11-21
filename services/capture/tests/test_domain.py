from dataclasses import replace

import pytest

from domain import (
    BrowserReservation,
    InvalidBrowserReservationRenewal,
    InvalidTaskClaimRenewal,
    PageTask,
    TaskClaim,
)


def test_task_claim_accepts_a_renewal_that_preserves_ownership_and_extends_lease() -> None:
    claim = TaskClaim(
        task=PageTask("archive-1", "url-1", "https://example.org/", 0),
        attempt_id="attempt-1",
        fence=3,
        lease_until=150,
    )

    renewed = replace(claim, lease_until=200)

    claim.verify_renewal(renewed, now=100)


def test_task_claim_rejects_a_renewal_that_changes_its_fencing_generation() -> None:
    claim = TaskClaim(
        task=PageTask("archive-1", "url-1", "https://example.org/", 0),
        attempt_id="attempt-1",
        fence=3,
        lease_until=150,
    )

    with pytest.raises(InvalidTaskClaimRenewal):
        claim.verify_renewal(replace(claim, fence=4, lease_until=200), now=100)


def test_task_claim_rejects_a_renewal_that_does_not_extend_the_lease() -> None:
    claim = TaskClaim(
        task=PageTask("archive-1", "url-1", "https://example.org/", 0),
        attempt_id="attempt-1",
        fence=3,
        lease_until=150,
    )

    with pytest.raises(InvalidTaskClaimRenewal):
        claim.verify_renewal(replace(claim, lease_until=150), now=100)


def test_browser_reservation_accepts_a_renewal_that_preserves_ownership() -> None:
    reservation = BrowserReservation(
        attempt_id="attempt-1",
        reservation_id="reservation-1",
        slot_id="slot-2",
        fence=3,
        lease_until=150,
    )

    renewed = replace(reservation, lease_until=200)

    reservation.verify_renewal(renewed, now=100)


def test_browser_reservation_rejects_a_renewal_for_a_different_slot() -> None:
    reservation = BrowserReservation(
        attempt_id="attempt-1",
        reservation_id="reservation-1",
        slot_id="slot-2",
        fence=3,
        lease_until=150,
    )

    with pytest.raises(InvalidBrowserReservationRenewal):
        reservation.verify_renewal(
            replace(reservation, slot_id="slot-3", lease_until=200),
            now=100,
        )


def test_browser_reservation_rejects_a_renewal_with_an_expired_lease() -> None:
    reservation = BrowserReservation(
        attempt_id="attempt-1",
        reservation_id="reservation-1",
        slot_id="slot-2",
        fence=3,
        lease_until=150,
    )

    with pytest.raises(InvalidBrowserReservationRenewal):
        reservation.verify_renewal(
            replace(reservation, lease_until=140),
            now=160,
        )
