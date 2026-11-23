import { extractSearchableContent } from "../domain/content.js";
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

  if (extraction.kind === "UNSUPPORTED") {
    return {
      outcome: "UNSUPPORTED",
      snapshotId: page.snapshotId,
      reasonCode: extraction.reasonCode,
    };
  }

  await documentWriter.index(extraction.document);

  return { outcome: "INDEXED", snapshotId: page.snapshotId };
}

export { indexCapturedPage };
