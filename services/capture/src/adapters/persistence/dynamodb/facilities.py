import time
from typing import Any
from uuid import uuid4

from botocore.exceptions import ClientError

from .error_handling import (
    ConditionalWriteRejected,
    extract_cancellation_reasons,
    raise_unless_transaction_canceled,
)

EXPONENTIAL_BACKOFF_ATTEMPTS = 5

EXPONENTIAL_BACKOFF_DELAY = 0.01  # seconds


def new_lease_token() -> str:
    return str(uuid4())


def exponential_backoff(attempt: int) -> None:
    time.sleep(EXPONENTIAL_BACKOFF_DELAY * (2**attempt))


def transaction_request(
    items: list[dict[str, Any]],
    request_token: str | None,
) -> dict[str, Any]:
    request: dict[str, Any] = {"TransactItems": items}

    if request_token is not None:
        request["ClientRequestToken"] = request_token

    return request


def exponential_backoff_transact(
    client: Any,
    items: list[dict[str, Any]],
    request_token: str | None,
) -> None:
    for attempt in range(EXPONENTIAL_BACKOFF_ATTEMPTS):
        try:
            client.transact_write_items(**transaction_request(items, request_token))

            return
        except ClientError as error:
            raise_unless_transaction_canceled(error)

            codes = extract_cancellation_reasons(error)

            if "ConditionalCheckFailed" in codes:
                raise ConditionalWriteRejected from error

            if "TransactionConflict" not in codes or attempt == EXPONENTIAL_BACKOFF_ATTEMPTS - 1:
                raise

            exponential_backoff(attempt)
