import type { SearchDocument } from "../domain/index.js";

interface SearchDocumentWriter {
  index(document: SearchDocument): Promise<void>;

  deleteArchive(archiveId: string): Promise<void>;
}

export type { SearchDocumentWriter };
