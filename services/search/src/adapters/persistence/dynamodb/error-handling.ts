import { isRecord } from "../../../utils.js";

function allCancellationsAreConditional(error: Error): boolean {
  const reasons = (error as { CancellationReasons?: unknown })
    .CancellationReasons;

  return (
    Array.isArray(reasons) &&
    reasons.length > 0 &&
    reasons.every(
      (reason) =>
        isRecord(reason) && reason["Code"] === "ConditionalCheckFailed",
    )
  );
}

function isConditionalCheckFailure(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }

  return (
    error.name === "ConditionalCheckFailedException" ||
    (error.name === "TransactionCanceledException" &&
      allCancellationsAreConditional(error))
  );
}

export { isConditionalCheckFailure };
