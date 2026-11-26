import Fastify from "fastify";
import type { FastifyInstance } from "fastify";

import type { ManifestLedger } from "../ports/manifest-ledger.js";
import type { PublicationLedger } from "../ports/publication-ledger.js";
import type { SearchDocumentReader } from "../ports/search-reader.js";

import { HEALTH_READY_ROUTE } from "../common/routes.js";

import { mapError } from "./errors.js";
import { problem } from "./problem.js";

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

  server.setNotFoundHandler((_request, reply) =>
    reply
      .code(404)
      .type("application/problem+json")
      .send(problem(404, "Not Found", "the requested route does not exist")),
  );

  server.get(HEALTH_READY_ROUTE, () => ({ status: "ok" }));

  server.register(searchRoutes, {
    reader,
    publicationLedger,
    manifestLedger,
  });

  return server;
}

export { createSearchServer };
