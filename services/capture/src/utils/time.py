from datetime import UTC, datetime


def utc(t: datetime) -> str:
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
