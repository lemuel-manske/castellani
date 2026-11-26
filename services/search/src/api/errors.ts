import { errorCodes } from "fastify";

import { InvalidSearchCursorError } from "../ports/search-reader.js";

import { problem } from "./problem.js";
import type { ProblemDetails } from "./problem.js";

type ProblemMapper = (error: unknown) => ProblemDetails | null;

const problemMappers: readonly ProblemMapper[] = [
  (error) =>
    error instanceof InvalidSearchCursorError
      ? problem(400, "Invalid Search Cursor", "the cursor is invalid")
      : null,

  (error) =>
    error instanceof errorCodes.FST_ERR_VALIDATION
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
