import type { CapturedPage } from "../domain/content.js";

interface ArtifactReference {
  bucket: string;
  key: string;
  versionId?: string;
  sha256: string;
  sizeBytes: number;
}

interface CapturedPageReference {
  archiveId: string;
  snapshotId: string;
  url: string;
  finalUrl?: string;
  capturedAt: string;
  contentType?: string;
}

interface ArtifactObjectReader {
  getObject(reference: ArtifactReference): Promise<AsyncIterable<Uint8Array>>;
}

interface CapturedPageReader {
  read(
    page: CapturedPageReference,
    artifacts: readonly ArtifactReference[],
  ): Promise<CapturedPage>;
}

export type {
  ArtifactObjectReader,
  ArtifactReference,
  CapturedPageReader,
  CapturedPageReference,
};
