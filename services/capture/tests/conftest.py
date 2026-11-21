from collections.abc import Iterator

import pytest
from support.recording import LocalSite, start_local_site


pytest_plugins = ("support.local_dynamodb",)


@pytest.fixture
def local_site() -> Iterator[LocalSite]:
    site = start_local_site()

    try:
        yield site
    finally:
        site.stop()
