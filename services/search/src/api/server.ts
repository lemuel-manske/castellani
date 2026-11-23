import Fastify from "fastify";
import type { FastifyInstance } from "fastify";
import type { ManifestLedger } from "../ports/manifest-ledger.js";
import type { PublicationLedger } from "../ports/publication-ledger.js";
import type { SearchDocumentReader } from "../ports/search-reader.js";
import { mapError } from "./errors.js";
import { searchRoutes } from "./routes/search.js";

function createSearchServer(
  reader: SearchDocumentReader,
  publicationLedger: PublicationLedger,
  manifestLedger: ManifestLedger,
): FastifyInstance {
  const server = Fastify({ logger: false });

  server.setErrorHandler((error, _request, reply) => {
    const mapped = mapError(error);

    if (mapped.status >= 500) {
      reply.log.error({ err: error }, "Unhandled Search API error");
    }

    return reply
      .code(mapped.status)
      .type("application/problem+json")
      .send(mapped);
  });

  server.get("/health/ready", () => ({ status: "ok" }));

  server.register(searchRoutes, {
    reader,
    publicationLedger,
    manifestLedger,
  });

  return server;
}

export { createSearchServer };
