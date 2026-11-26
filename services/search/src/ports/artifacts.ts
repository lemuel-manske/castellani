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

class ArtifactIntegrityError extends Error {
  constructor(message: string) {
    super(message);

    this.name = "ArtifactIntegrityError";
  }
}

class CapturedResponseNotFoundError extends Error {
  constructor(snapshotId: string, targetUrl: string) {
    super(`no WARC response found for snapshot ${snapshotId} at ${targetUrl}`);

    this.name = "CapturedResponseNotFoundError";
  }
}

export {
  ArtifactIntegrityError,
  CapturedResponseNotFoundError,
};

export type {
  ArtifactObjectReader,
  ArtifactReference,
  CapturedPageReader,
  CapturedPageReference,
};
