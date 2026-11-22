import { extractSearchableContent } from "../domain/content.js";
import type {
  ArtifactReference,
  CapturedPageReader,
  CapturedPageReference,
} from "../ports/artifacts.js";
import type { SearchDocumentWriter } from "../ports/search-index.js";

type SnapshotIndexingResult =
  | { outcome: "INDEXED"; snapshotId: string }
  | {
      outcome: "UNSUPPORTED";
      snapshotId: string;
      reasonCode: "UNSUPPORTED_CONTENT_TYPE" | "EMPTY_CONTENT";
    };

async function indexCapturedPage(
  page: CapturedPageReference,
  artifacts: readonly ArtifactReference[],
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
export type { SnapshotIndexingResult };
