import { expect, it } from "vitest";

import { createSearchServer } from "../../src/api/server.js";
import type { ManifestLedger } from "../../src/ports/manifest-ledger.js";
import type { PublicationLedger } from "../../src/ports/publication-ledger.js";
import { HEALTH_READY_ROUTE } from "../../src/common/routes.js";
import type { SearchDocumentReader } from "../../src/ports/search-reader.js";

it("reports readiness through the health endpoint", async () => {
  const server = createSearchServer(
    {} as SearchDocumentReader,
    {} as PublicationLedger,
    {} as ManifestLedger,
  );

  const response = await server.inject({
    method: "GET",
    url: HEALTH_READY_ROUTE,
  });

  expect(response.statusCode).toBe(200);
  expect(response.json()).toEqual({ status: "ok" });

  const notFound = await server.inject({ method: "GET", url: "/missing" });

  expect(notFound.statusCode).toBe(404);
  expect(notFound.headers["content-type"]).toContain(
    "application/problem+json",
  );
  expect(notFound.json()).toEqual({
    type: "about:blank",
    title: "Not Found",
    status: 404,
    detail: "the requested route does not exist",
  });

  await server.close();
});
