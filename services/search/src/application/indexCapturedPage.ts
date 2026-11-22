import { readCapturedPage } from "../adapters/artifacts.js";
import type {
  ArtifactObjectReader,
  ArtifactReference,
  CapturedPageReference,
} from "../adapters/artifacts.js";
import { extractSearchableContent } from "../domain/content.js";
import type { SearchDocument } from "../domain/content.js";

interface SearchDocumentWriter {
  index(document: SearchDocument): Promise<void>;
}

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
  artifactReader: ArtifactObjectReader,
  documentWriter: SearchDocumentWriter,
): Promise<SnapshotIndexingResult> {
  const capturedPage = await readCapturedPage(page, artifacts, artifactReader);
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
export type { SearchDocumentWriter, SnapshotIndexingResult };
