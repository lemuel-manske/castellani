from capture.browser import extract_links


def test_extract_links_resolves_relative_urls() -> None:
    html = """
    <a href="/about">About</a>
    <a href="articles/first">First article</a>
    """

    links = extract_links(html, "https://example.org/start")

    assert links == (
        "https://example.org/about",
        "https://example.org/articles/first",
    )


def test_extract_links_preserves_absolute_urls() -> None:
    html = """
    <a href="https://example.org/archive">Archive</a>
    """

    links = extract_links(html, "https://example.org/start")

    assert links == ("https://example.org/archive",)


def test_extract_links_removes_duplicate_urls_preserving_first_occurrence() -> None:
    html = """
    <a href="/about">About</a>
    <a href="/archive">Archive</a>
    <a href="/about">About again</a>
    """

    links = extract_links(html, "https://example.org/start")

    assert links == (
        "https://example.org/about",
        "https://example.org/archive",
    )


def test_extract_links_ignores_non_http_urls() -> None:
    html = """
    <a href="mailto:contact@example.org">Email</a>
    <a href="javascript:void(0)">Script</a>
    """

    links = extract_links(html, "https://example.org/start")

    assert links == ()


def test_extract_links_ignores_empty_urls() -> None:
    html = """
    <a href="">Empty</a>
    <a>No href</a>
    """

    links = extract_links(html, "https://example.org/start")

    assert links == ()


def test_extract_links_returns_empty_tuple_when_no_links_exist() -> None:
    html = """
    <html>
      <body>
        <p>No links here.</p>
      </body>
    </html>
    """

    links = extract_links(html, "https://example.org/start")

    assert links == ()
