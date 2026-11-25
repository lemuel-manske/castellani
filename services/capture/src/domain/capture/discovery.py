from dataclasses import dataclass

from .task import PageTask
from .url_identity import URLIdentity, identify_url


@dataclass(frozen=True)
class DiscoveredPage:
    """A normalized navigational page discovered one hop from a parent task."""

    identity: URLIdentity
    depth: int

    def __post_init__(self) -> None:
        if self.depth < 0:
            raise ValueError("depth must not be negative")


def identify_discovered_pages(
    parent: PageTask,
    discovered_urls: tuple[str, ...],
) -> tuple[DiscoveredPage, ...]:
    """
    Normalize and deduplicate a page's outgoing navigational links.

    Discovery depth is derived from the parent's current minimum depth, not
    from the order in which a worker happened to encounter the URL.
    """

    depth = parent.depth + 1

    discovered: dict[str, DiscoveredPage] = {}

    for url in discovered_urls:
        try:
            identity = identify_url(url)
        except ValueError:
            continue

        discovered.setdefault(
            identity.url_key,
            DiscoveredPage(identity=identity, depth=depth),
        )

    return tuple(discovered.values())
