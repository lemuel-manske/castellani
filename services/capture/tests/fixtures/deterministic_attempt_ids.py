from itertools import count

import pytest

from adapters.persistence.dynamodb import task


@pytest.fixture
def deterministic_attempt_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    identifiers = count(1)

    monkeypatch.setattr(
        task,
        "new_attempt_id",
        lambda: f"attempt-{next(identifiers)}",
    )
