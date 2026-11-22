import type { FastifyReply, FastifyRequest } from "fastify";
import { searchPublishedDocuments } from "../../application/searchPublishedDocuments.js";
import type { ManifestLedger } from "../../ports/manifest-ledger.js";
import type { PublicationLedger } from "../../ports/publication-ledger.js";
import type { SearchDocumentReader } from "../../ports/search-reader.js";
import { problem } from "../problem.js";
import type { SearchQuery } from "../schemas/search.js";

interface SearchHandlerDependencies {
  reader: SearchDocumentReader;
  publicationLedger: PublicationLedger;
  manifestLedger: ManifestLedger;
}

async function handleSearch(
  request: FastifyRequest<{ Querystring: SearchQuery }>,
  reply: FastifyReply,
  { reader, publicationLedger, manifestLedger }: SearchHandlerDependencies,
) {
  const query = request.query;

  if (!query.q.trim()) {
    return reply
      .code(400)
      .type("application/problem+json")
      .send(problem(400, "Invalid Search", "q must not be empty"));
  }

  if (
    query.capturedFrom !== undefined &&
    query.capturedTo !== undefined &&
    Date.parse(query.capturedFrom) > Date.parse(query.capturedTo)
  ) {
    return reply
      .code(400)
      .type("application/problem+json")
      .send(
        problem(
          400,
          "Invalid Search",
          "capturedFrom must not exceed capturedTo",
        ),
      );
  }

  try {
    return await searchPublishedDocuments(
      {
        text: query.q,
        ...(query.collectionId ? { collectionId: query.collectionId } : {}),
        ...(query.archiveId ? { archiveId: query.archiveId } : {}),
        ...(query.snapshotId ? { snapshotId: query.snapshotId } : {}),
        ...(query.capturedFrom === undefined
          ? {}
          : { capturedFrom: query.capturedFrom }),
        ...(query.capturedTo === undefined
          ? {}
          : { capturedTo: query.capturedTo }),
        ...(query.limit === undefined ? {} : { limit: query.limit }),
        ...(query.cursor === undefined ? {} : { cursor: query.cursor }),
      },
      reader,
      publicationLedger,
      manifestLedger,
    );
  } catch (error) {
    const detail =
      error instanceof Error ? error.message : "search dependency failed";

    if (detail === "invalid search cursor") {
      return reply
        .code(400)
        .type("application/problem+json")
        .send(problem(400, "Invalid Search", detail));
    }

    request.log.error({ err: error }, "Search request failed");

    return reply
      .code(503)
      .type("application/problem+json")
      .send(
        problem(
          503,
          "Search Unavailable",
          "Search is temporarily unavailable.",
        ),
      );
  }
}

export { handleSearch };
export type { SearchHandlerDependencies };
