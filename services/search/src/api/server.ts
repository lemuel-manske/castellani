import Fastify from "fastify";
import type { FastifyInstance } from "fastify";
import { searchPublishedDocuments } from "../application/searchPublishedDocuments.js";
import type { ManifestLedger } from "../ports/manifest-ledger.js";
import type { PublicationLedger } from "../ports/publication-ledger.js";
import type { SearchDocumentReader } from "../ports/search-reader.js";

const SEARCH_QUERY_PARAMETERS = new Set([
  "q",
  "collectionId",
  "archiveId",
  "snapshotId",
  "capturedFrom",
  "capturedTo",
  "limit",
  "cursor",
]);

interface SearchRequest {
  text: string;
  collectionId?: string;
  archiveId?: string;
  snapshotId?: string;
  capturedFrom?: string;
  capturedTo?: string;
  limit?: number;
  cursor?: string;
}
type SearchRequestResult = { request: SearchRequest } | { error: string };

function isRfc3339(value: string): boolean {
  return (
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(
      value,
    ) && Number.isFinite(Date.parse(value))
  );
}

function parseSearchRequest(query: unknown): SearchRequestResult {
  if (typeof query !== "object" || query === null || Array.isArray(query)) {
    return { error: "query parameters must be key-value pairs" };
  }

  const values = query as Record<string, unknown>;
  const invalidParameter = Object.entries(values).find(
    ([key, value]) =>
      !SEARCH_QUERY_PARAMETERS.has(key) || typeof value !== "string",
  );

  if (invalidParameter)
    return { error: `invalid query parameter: ${invalidParameter[0]}` };

  const text = values.q;

  if (
    typeof text !== "string" ||
    text.trim().length === 0 ||
    text.length > 500
  ) {
    return { error: "q must contain between 1 and 500 characters" };
  }

  const limitValue = values.limit;
  const limit = limitValue === undefined ? undefined : Number(limitValue);

  if (
    limit !== undefined &&
    (!Number.isSafeInteger(limit) || limit < 1 || limit > 100)
  ) {
    return { error: "limit must be an integer between 1 and 100" };
  }

  const capturedFrom = values.capturedFrom as string | undefined;
  const capturedTo = values.capturedTo as string | undefined;

  if (
    (capturedFrom !== undefined && !isRfc3339(capturedFrom)) ||
    (capturedTo !== undefined && !isRfc3339(capturedTo))
  ) {
    return { error: "capturedFrom and capturedTo must be RFC3339 timestamps" };
  }

  if (
    capturedFrom &&
    capturedTo &&
    Date.parse(capturedFrom) > Date.parse(capturedTo)
  ) {
    return { error: "capturedFrom must not exceed capturedTo" };
  }

  const cursor = values.cursor as string | undefined;

  if (
    cursor !== undefined &&
    (cursor.length > 2048 || !/^[A-Za-z0-9_-]+$/.test(cursor))
  ) {
    return { error: "cursor is invalid" };
  }

  const optional = (key: string): string | undefined => {
    const value = values[key] as string | undefined;

    return value === undefined || value.length === 0 ? undefined : value;
  };

  return {
    request: {
      text,
      ...(optional("collectionId") === undefined
        ? {}
        : { collectionId: optional("collectionId") }),
      ...(optional("archiveId") === undefined
        ? {}
        : { archiveId: optional("archiveId") }),
      ...(optional("snapshotId") === undefined
        ? {}
        : { snapshotId: optional("snapshotId") }),
      ...(capturedFrom === undefined ? {} : { capturedFrom }),
      ...(capturedTo === undefined ? {} : { capturedTo }),
      ...(limit === undefined ? {} : { limit }),
      ...(cursor === undefined ? {} : { cursor }),
    },
  };
}

function problem(status: number, title: string, detail: string) {
  return { type: "about:blank", title, status, detail };
}

function createSearchServer(
  reader: SearchDocumentReader,
  publicationLedger: PublicationLedger,
  manifestLedger: ManifestLedger,
): FastifyInstance {
  const server = Fastify({ logger: false });

  server.get("/search", async (request, reply) => {
    const parsed = parseSearchRequest(request.query);

    if ("error" in parsed) {
      return reply
        .code(400)
        .type("application/problem+json")
        .send(problem(400, "Invalid Search", parsed.error));
    }

    try {
      return await searchPublishedDocuments(
        parsed.request,
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
  });
  return server;
}

export { createSearchServer, parseSearchRequest };
