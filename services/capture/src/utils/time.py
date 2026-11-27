from datetime import UTC, datetime


def utc(t: datetime) -> str:
    """
    Convert a datetime to a UTC ISO 8601 string.
    """

    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    """
    Get the current UTC time as an ISO 8601 string.
    """

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
