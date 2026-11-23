import { expect, it } from "vitest";

import { mapError } from "../../src/api/errors.js";

it("maps Fastify validation errors by their code", () => {
  const mapped = mapError({ code: "FST_ERR_VALIDATION" });

  expect(mapped).toEqual({
    type: "about:blank",
    title: "Invalid Search",
    status: 400,
    detail: "query parameters are invalid",
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
