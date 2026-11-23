import { expect, it } from "vitest";

import { createSearchServer } from "../../src/api/server.js";
import type { ManifestLedger } from "../../src/ports/manifest-ledger.js";
import type { PublicationLedger } from "../../src/ports/publication-ledger.js";
import type { SearchDocumentReader } from "../../src/ports/search-reader.js";

it("reports readiness through the health endpoint", async () => {
  const server = createSearchServer(
    {} as SearchDocumentReader,
    {} as PublicationLedger,
    {} as ManifestLedger,
  );

  const response = await server.inject({ method: "GET", url: "/health/ready" });

  expect(response.statusCode).toBe(200);
  expect(response.json()).toEqual({ status: "ok" });

  await server.close();
});
