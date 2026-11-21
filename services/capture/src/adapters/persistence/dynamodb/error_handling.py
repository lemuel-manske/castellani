from typing import TypedDict

from botocore.exceptions import ClientError  # pyright: ignore[reportMissingTypeStubs]


class ClientErrorResponse(TypedDict):
    """
    Just for type-safety.
    """

    Error: dict[str, str]


def is_conditional_failure(error: ClientError) -> bool:
    response: ClientErrorResponse = error.response

    return response["Error"]["Code"] == "ConditionalCheckFailedException"


def is_transaction_canceled(error: ClientError) -> bool:
    response: ClientErrorResponse = error.response

    return response["Error"]["Code"] == "TransactionCanceledException"


def extract_cancellation_reasons(error: ClientError) -> set[str]:
    response: ClientErrorResponse = error.response

    reasons = response.get("CancellationReasons", [])
    codes = {reason.get("Code") for reason in reasons}

    return codes
