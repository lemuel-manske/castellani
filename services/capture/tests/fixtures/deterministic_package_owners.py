from itertools import count

import pytest

from adapters.persistence.dynamodb import publication


@pytest.fixture
def deterministic_package_owners(monkeypatch: pytest.MonkeyPatch) -> None:
    owners = count(1)

    monkeypatch.setattr(
        publication,
        "uuid4",
        lambda: f"owner-{next(owners)}",
    )
