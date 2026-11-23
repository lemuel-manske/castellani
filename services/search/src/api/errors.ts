import { problem } from "./problem.js";
import type { ProblemDetails } from "./problem.js";

const VALIDATION_ERROR_CODE = "FST_ERR_VALIDATION";

interface CodedError {
  readonly code: string;
}

type ProblemMapper = (error: unknown) => ProblemDetails | null;

function isCodedError(error: unknown): error is CodedError {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string"
  );
}

const problemMappers: readonly ProblemMapper[] = [
  (error) =>
    isCodedError(error) && error.code === VALIDATION_ERROR_CODE
      ? problem(400, "Invalid Search", "query parameters are invalid")
      : null,
];

function mapError(error: unknown): ProblemDetails {
  for (const mapper of problemMappers) {
    const mapped = mapper(error);

    if (mapped !== null) {
      return mapped;
    }
  }

  return problem(500, "Internal Server Error", "an unexpected error occurred");
}

export { mapError, problemMappers };

export type { ProblemMapper };
