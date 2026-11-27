# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
from io import BytesIO

from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter


def warc_bytes(url: str = "https://example.org/") -> bytes:
    buffer = BytesIO()

    writer = WARCWriter(buffer, gzip=True)

    headers = StatusAndHeaders(
        "200 OK",
        [("Content-Type", "text/html")],
        protocol="HTTP/1.1",
    )

    record = writer.create_warc_record(
        url,
        "response",
        payload=BytesIO(b"<html><body>Archived page</body></html>"),
        http_headers=headers,
    )

    writer.write_record(record)

    return buffer.getvalue()
