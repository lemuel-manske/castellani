import {
  CONTENT_EXTRACTION_KIND,
  INDEXING_OUTCOME,
  extractSearchableContent,
} from "../domain/index.js";
import type {
  ArtifactReference,
  CapturedPageReader,
  CapturedPageReference,
} from "../ports/artifacts.js";
import type { SearchDocumentWriter } from "../ports/search-index.js";

import { SnapshotIndexingResult } from "./types.js";

async function indexCapturedPage(
  page: CapturedPageReference,
  artifacts: ArtifactReference[],
  capturedPageReader: CapturedPageReader,
  documentWriter: SearchDocumentWriter,
): Promise<SnapshotIndexingResult> {
  const capturedPage = await capturedPageReader.read(page, artifacts);

  const extraction = extractSearchableContent(capturedPage);

  if (extraction.kind === CONTENT_EXTRACTION_KIND.UNSUPPORTED) {
    return {
      outcome: INDEXING_OUTCOME.UNSUPPORTED,
      snapshotId: page.snapshotId,
      reasonCode: extraction.reasonCode,
    };
  }

  await documentWriter.index(extraction.document);

  return {
    outcome: INDEXING_OUTCOME.INDEXED,
    snapshotId: page.snapshotId,
  };
}

export { indexCapturedPage };
