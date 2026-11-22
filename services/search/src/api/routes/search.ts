import type { FastifyPluginAsync } from "fastify";
import { handleSearch } from "../handlers/search.js";
import type { SearchHandlerDependencies } from "../handlers/search.js";
import { searchQuerySchema } from "../schemas/search.js";
import type { SearchQuery } from "../schemas/search.js";

const searchRoutes: FastifyPluginAsync<SearchHandlerDependencies> = async (
  server,
  dependencies,
) => {
  server.route<{ Querystring: SearchQuery }>({
    method: "GET",
    url: "/search",
    schema: {
      querystring: searchQuerySchema,
    },
    handler: (request, reply) => handleSearch(request, reply, dependencies),
  });
};

export { searchRoutes };
