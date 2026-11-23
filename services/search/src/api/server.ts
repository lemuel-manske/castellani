import Fastify from "fastify";
import type { FastifyInstance } from "fastify";
import type { ManifestLedger } from "../ports/manifest-ledger.js";
import type { PublicationLedger } from "../ports/publication-ledger.js";
import type { SearchDocumentReader } from "../ports/search-reader.js";
import { problem } from "./problem.js";
import { searchRoutes } from "./routes/search.js";

function createSearchServer(
  reader: SearchDocumentReader,
  publicationLedger: PublicationLedger,
  manifestLedger: ManifestLedger,
): FastifyInstance {
  const server = Fastify({ logger: false });

  server.setErrorHandler((error, _request, reply) => {
    const err = error instanceof Error ? error : new Error(String(error));

    if ("validation" in err && err.validation !== undefined) {
      return reply
        .code(400)
        .type("application/problem+json")
        .send(problem(400, "Invalid Search", "query parameters are invalid"));
    }

    reply.log.error({ err }, "Unhandled Search API error");

    return reply
      .code(500)
      .type("application/problem+json")
      .send(
        problem(500, "Internal Server Error", "an unexpected error occurred"),
      );
  });

  server.get("/health/ready", async () => ({ status: "ok" }));

  server.register(searchRoutes, {
    reader,
    publicationLedger,
    manifestLedger,
  });

  return server;
}

export { createSearchServer };
