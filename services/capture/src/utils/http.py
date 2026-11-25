from datetime import UTC, datetime
from email.utils import format_datetime

from domain.capture import InvalidWACZRange


def http_last_modified(value: datetime | None) -> str | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)

    return format_datetime(value, usegmt=True)


def normalize_etag(value: str) -> str:
    return value.removeprefix("W/").strip('"')


def parse_range(header: str, content_length: int) -> tuple[int, int | None]:
    if not header.startswith("bytes=") or "," in header:
        raise InvalidWACZRange

    try:
        start_text, end_text = header[6:].split("-", 1)

        if not start_text:
            suffix_length = int(end_text)

            if suffix_length < 1:
                raise InvalidWACZRange

            return max(0, content_length - suffix_length), content_length - 1

        start = int(start_text)
        end = int(end_text) if end_text else None
    except ValueError as error:
        raise InvalidWACZRange from error

    if start < 0 or (end is not None and end < start):
        raise InvalidWACZRange

    return start, end
