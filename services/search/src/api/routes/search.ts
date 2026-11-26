import type { FastifyPluginAsync } from "fastify";

import { SEARCH_ROUTE } from "../../common/routes.js";

import { handleSearch } from "../handlers/search.js";
import type { SearchHandlerDependencies } from "../handlers/search.js";

import { searchQuerySchema } from "../schemas/search.js";
import type { SearchQuery } from "../schemas/search.js";

const GET_METHOD = "GET";

const searchRoutes: FastifyPluginAsync<SearchHandlerDependencies> = (
  server,
  dependencies,
) => {
  server.route<{ Querystring: SearchQuery }>({
    method: GET_METHOD,
    url: SEARCH_ROUTE,
    schema: {
      querystring: searchQuerySchema,
    },
    handler: (request) => handleSearch(request, dependencies),
  });

  return Promise.resolve();
};

export { searchRoutes };
