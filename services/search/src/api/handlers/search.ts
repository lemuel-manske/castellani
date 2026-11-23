import type { FastifyRequest } from "fastify";

import { searchPublishedDocuments } from "../../application/searchPublishedDocuments.js";

import type { ManifestLedger } from "../../ports/manifest-ledger.js";
import type { PublicationLedger } from "../../ports/publication-ledger.js";
import type { SearchDocumentReader } from "../../ports/search-reader.js";

import type { SearchQuery } from "../schemas/search.js";

import { SearchPublishedDocumentsInput } from "../../application/types.js";

type SearchHandlerDependencies = {
  reader: SearchDocumentReader;
  publicationLedger: PublicationLedger;
  manifestLedger: ManifestLedger;
};

async function handleSearch(
  request: FastifyRequest<{ Querystring: SearchQuery }>,
  { reader, publicationLedger, manifestLedger }: SearchHandlerDependencies,
) {
  const query = request.query;

  const queryParsed: SearchPublishedDocumentsInput = {
    text: query.q,
    collectionId: query.collectionId,
    archiveId: query.archiveId,
    snapshotId: query.snapshotId,
    capturedFrom: query.capturedFrom,
    capturedTo: query.capturedTo,
    limit: query.limit,
    cursor: query.cursor,
  };

  return searchPublishedDocuments(
    queryParsed,
    reader,
    publicationLedger,
    manifestLedger,
  );
}

export { handleSearch };

export type { SearchHandlerDependencies };
