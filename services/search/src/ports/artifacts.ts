import type { CapturedPage } from "../domain/content.js";
import { createSchemaValidator } from "../schema.js";

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

const ArtifactReferenceSchema = {
  type: "object",
  properties: {
    bucket: { type: "string", minLength: 1 },
    key: { type: "string", minLength: 1 },
    versionId: { type: "string", minLength: 1, nullable: true },
    sha256: { type: "string", pattern: "^[a-f0-9]{64}$" },
    sizeBytes: { type: "integer", minimum: 0 },
  },
  required: ["bucket", "key", "sha256", "sizeBytes"],
  additionalProperties: false,
} as const;

const artifactReferenceValidator = createSchemaValidator<ArtifactReference>(
  ArtifactReferenceSchema,
);

function isArtifactReference(value: unknown): value is ArtifactReference {
  return artifactReferenceValidator.validate(value);
}

export {
  ArtifactIntegrityError,
  CapturedResponseNotFoundError,
  ArtifactReferenceSchema,
  isArtifactReference,
};

export type {
  ArtifactObjectReader,
  ArtifactReference,
  CapturedPageReader,
  CapturedPageReference,
};
