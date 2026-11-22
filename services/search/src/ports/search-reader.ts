import type { SearchDocument } from "../domain/content.js";

interface SearchQuery {
  text: string;
  collectionId?: string;
  archiveId?: string;
  snapshotId?: string;
  capturedFrom?: string;
  capturedTo?: string;
}

interface SearchDocumentCandidate {
  document: SearchDocument;
  score: number;
  snippet: string;
  cursor: string;
}

interface SearchDocumentPage {
  candidates: SearchDocumentCandidate[];
  nextCursor: string | null;
}

interface SearchDocumentReader {
  search(
    query: SearchQuery,
    limit: number,
    cursor?: string,
  ): Promise<SearchDocumentPage>;
}

export type {
  SearchDocumentCandidate,
  SearchDocumentPage,
  SearchDocumentReader,
  SearchQuery,
};
