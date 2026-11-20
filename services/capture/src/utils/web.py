import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

HTTP_SCHEMES = {"http", "https"}

MAX_PORT = 65_535

HTTPS_PORT = 443
HTTP_PORT = 80

SCHEME_TO_PORT = {
    "http": HTTP_PORT,
    "https": HTTPS_PORT,
}


def is_valid_url(url: str) -> bool:
    """
    Returns whether the given URL is valid and safe to request.
    """

    try:
        parsed_url = urlsplit(url)

        if (
            parsed_url.scheme not in HTTP_SCHEMES
            or not parsed_url.hostname
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            return False

        port = parsed_url.port

        if port is not None and not 0 <= port <= MAX_PORT:
            return False
    except ValueError:
        return False

    return True


async def is_safe_request_url(url: str, allow_private_networks: bool = False) -> bool:
    """
    Reject unsafe destinations; production egress policy must enforce IPs too.

    The recorder resolves hostnames independently, so this application-level DNS check
    is defense in depth and does not by itself prevent DNS rebinding.
    """

    if not is_valid_url(url):
        return False

    if allow_private_networks:
        return True

    parsed_url = urlsplit(url)
    hostname = parsed_url.hostname

    if hostname is None:
        return False

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        port = parsed_url.port or SCHEME_TO_PORT.get(parsed_url.scheme)

        try:
            records = await asyncio.get_running_loop().getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except OSError:
            return False

        addresses = {ipaddress.ip_address(record[4][0]) for record in records}

        return bool(addresses) and all(address.is_global for address in addresses)

    return address.is_global


def is_html_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return True

    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()

    return media_type in {"text/html", "application/xhtml+xml"}


def is_pdf_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False

    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()

    return media_type == "application/pdf"
