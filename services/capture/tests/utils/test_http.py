from datetime import datetime, timedelta, timezone

from utils.http import http_last_modified


def test_http_last_modified_normalizes_non_utc_offsets() -> None:
    value = datetime(2026, 11, 24, 12, 0, tzinfo=timezone(timedelta(hours=2)))

    assert http_last_modified(value) == "Tue, 24 Nov 2026 10:00:00 GMT"


def test_http_last_modified_treats_naive_datetimes_as_utc() -> None:
    assert http_last_modified(datetime(2026, 11, 24, 10, 0)) == "Tue, 24 Nov 2026 10:00:00 GMT"
