from collections.abc import Iterator

import pytest
pytest_plugins = ("support.local_dynamodb",)
from support.recording import LocalSite, start_local_site


@pytest.fixture
def local_site() -> Iterator[LocalSite]:
    site = start_local_site()

    try:
        yield site
    finally:
        site.stop()
