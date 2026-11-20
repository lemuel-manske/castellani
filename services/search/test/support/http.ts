import type { FastifyInstance } from "fastify";
import { afterEach } from "vitest";

import { buildServer, type Searcher } from "../../src/http/server.js";
import { SearchUnavailableError, type SearchPage } from "../../src/search/opensearch.js";
import type { SearchQuery } from "../../src/search/query.js";

/** Search backend double that records received queries. */
export class StubSearcher implements Searcher {
  readonly queries: SearchQuery[] = [];
  page: SearchPage = { results: [], nextCursor: null };
  unavailable = false;

  search(query: SearchQuery): Promise<SearchPage> {
    this.queries.push(query);

    if (this.unavailable) {
      return Promise.reject(new SearchUnavailableError("connect ECONNREFUSED"));
    }

    return Promise.resolve(this.page);
  }
}

const servers: FastifyInstance[] = [];

afterEach(async () => {
  await Promise.all(servers.splice(0).map((server) => server.close()));
});

export function startServer(searcher: Searcher, ready = true): FastifyInstance {
  const server = buildServer({ searcher, ready: () => ready });
  servers.push(server);

  return server;
}

export async function get(server: FastifyInstance, url: string) {
  const response = await server.inject({ method: "GET", url });

  return {
    status: response.statusCode,
    mediaType: String(response.headers["content-type"]).split(";", 1)[0],
    text: response.body,
    json: () => response.json<Record<string, unknown>>(),
  };
}
