from datetime import UTC, datetime, timedelta


def utc(t: datetime, delta: timedelta | None = None) -> str:
    """
    Convert a datetime to a UTC ISO 8601 string.
    """

    return (
        (t + delta if delta is not None else t).astimezone(UTC).isoformat().replace("+00:00", "Z")
    )


def utc_now(delta: timedelta | None = None) -> str:
    """
    Get the current UTC time as an ISO 8601 string.
    """

    return utc(datetime.now(UTC), delta)
