from collections.abc import Iterator

import pytest
from support.recording import LocalSite, start_local_site
from support.local_dynamodb import dynamodb_client  # noqa: F401


@pytest.fixture
def local_site() -> Iterator[LocalSite]:
    site = start_local_site()

    try:
        yield site
    finally:
        site.stop()
