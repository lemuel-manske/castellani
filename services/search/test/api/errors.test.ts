import { errorCodes } from "fastify";
import { expect, it } from "vitest";

import { mapError } from "../../src/api/errors.js";
import { InvalidSearchCursorError } from "../../src/ports/search-reader.js";

it("maps Fastify validation errors", () => {
  const mapped = mapError(errorCodes.FST_ERR_VALIDATION());

  expect(mapped).toEqual({
    type: "about:blank",
    title: "Invalid Search",
    status: 400,
    detail: "query parameters are invalid",
  });
});

it("maps invalid search cursors to a client error", () => {
  const mapped = mapError(new InvalidSearchCursorError());

  expect(mapped).toEqual({
    type: "about:blank",
    title: "Invalid Search Cursor",
    status: 400,
    detail: "the cursor is invalid",
  });
});

it("falls back to an internal problem for unknown errors", () => {
  const mapped = mapError(new Error("boom"));

  expect(mapped).toEqual({
    type: "about:blank",
    title: "Internal Server Error",
    status: 500,
    detail: "an unexpected error occurred",
  });
});
