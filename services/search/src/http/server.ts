import Fastify, { type FastifyInstance, type FastifyReply, type FastifyRequest } from "fastify";

import { type SearchPage, SearchUnavailableError } from "../search/opensearch.js";
import { type SearchQuery, InvalidQueryError, parseSearchQuery } from "../search/query.js";

export const PROBLEM_TYPE_PREFIX = "urn:distributed-web-archive:problem:";

const HEALTH_MEDIA_TYPE = "text/plain; charset=utf-8";

export type Searcher = { search(query: SearchQuery): Promise<SearchPage> };

export type ServerDependencies = {
  searcher: Searcher;
  ready: () => boolean;
  logger?: boolean | object;
};

export function buildServer({ searcher, ready, logger = false }: ServerDependencies): FastifyInstance {
  const app = Fastify({ logger, return503OnClosing: true });

  app.get("/health/live", async (_request, reply) => reply.type(HEALTH_MEDIA_TYPE).send("ok\n"));

  app.get("/health/ready", async (_request, reply) =>
    ready()
      ? reply.type(HEALTH_MEDIA_TYPE).send("ok\n")
      : reply.code(503).type(HEALTH_MEDIA_TYPE).send("unavailable\n"),
  );

  app.get("/search", async (request, reply) => {
    let query: SearchQuery;

    try {
      query = parseSearchQuery(request.query as Record<string, unknown>);
    } catch (error) {
      if (error instanceof InvalidQueryError) {
        return problem(request, reply, 400, "invalid-search", "Invalid Search", error.message);
      }

      throw error;
    }

    let page: SearchPage;

    try {
      page = await searcher.search(query);
    } catch (error) {
      if (error instanceof InvalidQueryError) {
        return problem(request, reply, 400, "invalid-search", "Invalid Search", error.message);
      }

      if (error instanceof SearchUnavailableError) {
        request.log.warn({ err: error }, "search unavailable");

        return problem(
          request,
          reply,
          503,
          "search-unavailable",
          "Search Unavailable",
          "The search index is unavailable.",
        );
      }

      throw error;
    }

    return reply.header("cache-control", "no-store").send(page);
  });

  app.setNotFoundHandler((request, reply) =>
    problem(request, reply, 404, "not-found", "Not Found", "The requested resource does not exist."),
  );

  app.setErrorHandler((error, request, reply) => {
    request.log.error({ err: error }, "unhandled request error");

    return problem(request, reply, 500, "internal", "Internal Server Error", "The request could not be completed.");
  });

  return app;
}

function problem(
  request: FastifyRequest,
  reply: FastifyReply,
  status: number,
  kind: string,
  title: string,
  detail: string,
): FastifyReply {
  return reply
    .code(status)
    .header("cache-control", "no-store")
    .type("application/problem+json")
    .send({ type: PROBLEM_TYPE_PREFIX + kind, title, status, detail, instance: request.url.split("?", 1)[0] });
}
