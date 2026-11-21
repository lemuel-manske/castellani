from collections.abc import Iterator

import pytest
from support.local_dynamodb import dynamodb_client  # noqa: F401
from support.recording import LocalSite, start_local_site


@pytest.fixture
def local_site() -> Iterator[LocalSite]:
    site = start_local_site()

    try:
        yield site
    finally:
        site.stop()
