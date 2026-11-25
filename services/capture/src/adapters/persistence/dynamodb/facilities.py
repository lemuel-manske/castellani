import time
from typing import Any
from uuid import uuid4

from botocore.exceptions import ClientError

from .error_handling import (
    ConditionalWriteRejected,
    extract_cancellation_reasons,
    is_transaction_canceled,
)

EXPONENTIAL_BACKOFF_ATTEMPTS = 5

EXPONENTIAL_BACKOFF_DELAY = 0.01  # seconds


def new_lease_token() -> str:
    return str(uuid4())


def exponential_backoff_transact(
    client: Any,
    items: list[dict[str, Any]],
    request_token: str | None,
) -> None:
    for attempt in range(EXPONENTIAL_BACKOFF_ATTEMPTS):
        try:
            request: dict[str, Any] = {"TransactItems": items}

            if request_token is not None:
                request["ClientRequestToken"] = request_token

            client.transact_write_items(**request)

            return
        except ClientError as error:
            if not is_transaction_canceled(error):
                raise

            codes = extract_cancellation_reasons(error)

            if "ConditionalCheckFailed" in codes:
                raise ConditionalWriteRejected from error

            if "TransactionConflict" not in codes or attempt == 4:
                raise

            time.sleep(EXPONENTIAL_BACKOFF_DELAY * (2**attempt))
