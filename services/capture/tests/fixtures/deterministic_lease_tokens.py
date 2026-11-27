from itertools import count

import pytest

from adapters.persistence.dynamodb import outbox


@pytest.fixture
def deterministic_lease_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    tokens = count(1)

    monkeypatch.setattr(
        outbox,
        "new_lease_token",
        lambda: f"lease-{next(tokens)}",
    )
