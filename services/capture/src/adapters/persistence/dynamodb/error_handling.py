from botocore.exceptions import ClientError


class ConditionalWriteRejected(RuntimeError):
    """Raised when a DynamoDB transaction is rejected due to a conditional failure."""


def is_conditional_failure(error: ClientError) -> bool:
    response = error.response

    return response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def is_transaction_canceled(error: ClientError) -> bool:
    response = error.response

    return response.get("Error", {}).get("Code") == "TransactionCanceledException"


def extract_cancellation_reasons(error: ClientError) -> set[str]:
    response = error.response

    reasons = response.get("CancellationReasons", [])
    codes = {reason.get("Code") for reason in reasons}

    return {code for code in codes if code is not None}
