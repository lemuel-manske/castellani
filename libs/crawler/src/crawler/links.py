from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from .fn import is_valid_url
from .results import DiscoveredLinkLimitExceeded

DEFAULT_MAX_DISCOVERED_LINKS = 1_000


def extract_links(
    html: str,
    base_url: str,
    max_links: int = DEFAULT_MAX_DISCOVERED_LINKS,
) -> tuple[str, ...]:
    document = HTMLParser(html)

    discovered: dict[str, None] = {}

    for anchor in document.css("a[href]"):
        href = anchor.attributes.get("href", "")

        if not href:
            continue

        href = href.strip()

        try:
            absolute_url = urljoin(base_url, href)
        except ValueError:
            continue

        if not is_valid_url(absolute_url) or absolute_url in discovered:
            continue

        if len(discovered) >= max_links:
            raise DiscoveredLinkLimitExceeded(
                f"page exceeded the discovered-link limit of {max_links}",
            )

        discovered.setdefault(absolute_url, None)

    return tuple(discovered)


__all__ = [
    "extract_links",
]
