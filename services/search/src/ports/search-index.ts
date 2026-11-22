import type { SearchDocument } from "../domain/content.js";

interface SearchDocumentWriter {
  index(document: SearchDocument): Promise<void>;
}

export type { SearchDocumentWriter };
