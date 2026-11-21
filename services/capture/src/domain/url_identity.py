import ipaddress
import re
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import quote, urlsplit, urlunsplit

URL_IDENTITY_VERSION = 1
HTTP_SCHEMES = {"http", "https"}
DEFAULT_PORTS = {"http": 80, "https": 443}
UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


class InvalidURLIdentity(ValueError):
    """Raised when a URL cannot be used as a crawl navigation identity."""


@dataclass(frozen=True)
class URLIdentity:
    """Versioned identities for fetching and navigating to one discovered URL."""

    discovery_url: str
    fetch_url: str
    navigation_url: str
    url_key: str


def identify_url(url: str) -> URLIdentity:
    if not url:
        raise InvalidURLIdentity("url must not be empty")

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise InvalidURLIdentity("url must be a valid absolute HTTP(S) URL") from error

    scheme = parsed.scheme.lower()

    if (
        scheme not in HTTP_SCHEMES
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and not 1 <= port <= 65_535)
    ):
        raise InvalidURLIdentity("url must be a valid absolute HTTP(S) URL without credentials")

    hostname = _normalize_hostname(parsed.hostname)
    default_port = DEFAULT_PORTS[scheme]
    authority = f"[{hostname}]" if ":" in hostname else hostname

    if port is not None and port != default_port:
        authority = f"{authority}:{port}"

    path = _normalize_component(parsed.path or "/", safe="/:@!$&'()*+,;=-._~")
    path = _remove_dot_segments(path)

    if not path:
        path = "/"

    query = _normalize_component(parsed.query, safe="/?:@!$&'()*+,;=-._~+")
    fetch_url = urlunsplit((scheme, authority, path, query, ""))

    fragment = _normalize_component(parsed.fragment, safe="/?:@!$&'()*+,;=-._~+")
    navigation_fragment = fragment if fragment.startswith("/") or fragment.startswith("!/") else ""
    navigation_url = (
        f"{fetch_url}#{navigation_fragment}" if navigation_fragment else fetch_url
    )

    identity = f"url-v{URL_IDENTITY_VERSION}:{navigation_url}"
    digest = sha256(identity.encode("utf-8")).hexdigest()

    return URLIdentity(
        discovery_url=url,
        fetch_url=fetch_url,
        navigation_url=navigation_url,
        url_key=f"v{URL_IDENTITY_VERSION}-{digest}",
    )


def _normalize_hostname(hostname: str) -> str:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            return hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as error:
            raise InvalidURLIdentity("url hostname must be valid IDNA") from error

    return address.compressed.lower()


def _normalize_component(value: str, safe: str) -> str:
    value = re.sub(r"%(?![0-9A-Fa-f]{2})", "%25", value)

    def normalize_escape(match: re.Match[str]) -> str:
        character = chr(int(match.group(1), 16))

        if character in UNRESERVED:
            return character

        return f"%{match.group(1).upper()}"

    value = re.sub(r"%([0-9A-Fa-f]{2})", normalize_escape, value)

    return quote(value, safe=f"{safe}%")


def _remove_dot_segments(path: str) -> str:
    remaining = path
    normalized = ""

    while remaining:
        if remaining.startswith("../"):
            remaining = remaining[3:]
        elif remaining.startswith("./"):
            remaining = remaining[2:]
        elif remaining.startswith("/./"):
            remaining = remaining[2:]
        elif remaining == "/.":
            remaining = "/"
        elif remaining.startswith("/../"):
            remaining = remaining[3:]
            normalized = _remove_last_segment(normalized)
        elif remaining == "/..":
            remaining = "/"
            normalized = _remove_last_segment(normalized)
        elif remaining in {".", ".."}:
            remaining = ""
        else:
            start = 1 if remaining.startswith("/") else 0
            next_separator = remaining.find("/", start)
            if next_separator == -1:
                normalized += remaining
                remaining = ""
            else:
                normalized += remaining[:next_separator]
                remaining = remaining[next_separator:]

    return normalized


def _remove_last_segment(path: str) -> str:
    separator = path.rfind("/")

    return path[:separator] if separator >= 0 else ""
