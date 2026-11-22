from domain import PageTask, identify_discovered_pages


def test_discovery_normalizes_and_deduplicates_navigation_identity() -> None:
    parent = PageTask("archive-1", "parent", "https://example.org/", 2)

    discovered = identify_discovered_pages(
        parent,
        (
            "https://EXAMPLE.org:443/a/../b",
            "https://example.org/b",
            "https://example.org/b#section",
            "https://example.org/b#/dashboard",
        ),
    )

    assert len(discovered) == 2
    assert discovered[0].identity.navigation_url == "https://example.org/b"
    assert discovered[0].identity.fetch_url == "https://example.org/b"
    assert discovered[0].depth == 3
    assert discovered[1].identity.navigation_url == "https://example.org/b#/dashboard"


def test_discovery_preserves_distinct_hash_routes() -> None:
    parent = PageTask("archive-1", "parent", "https://example.org/", 0)

    discovered = identify_discovered_pages(
        parent,
        (
            "https://example.org/#/settings",
            "https://example.org/#/dashboard",
        ),
    )

    assert [page.identity.navigation_url for page in discovered] == [
        "https://example.org/#/settings",
        "https://example.org/#/dashboard",
    ]


def test_discovery_ignores_invalid_urls_without_failing_the_capture() -> None:
    parent = PageTask("archive-1", "parent", "https://example.org/", 0)

    discovered = identify_discovered_pages(
        parent,
        (
            "mailto:person@example.org",
            "javascript:alert(1)",
            "https://example.org/valid",
        ),
    )

    assert len(discovered) == 1
    assert discovered[0].identity.navigation_url == "https://example.org/valid"


def test_discovery_uses_parent_minimum_depth_plus_one() -> None:
    parent = PageTask("archive-1", "parent", "https://example.org/", 4)

    discovered = identify_discovered_pages(parent, ("https://example.org/child",))

    assert discovered[0].depth == 5
