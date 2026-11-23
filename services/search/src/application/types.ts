import type {
  CompensationDecision,
  PublicationIdentity,
  TerminalIndexingOutcome,
} from "../domain.js";
import {
  ArtifactReferenceSchema,
} from "../ports/artifacts.js";
import type {
  ArtifactReference,
  CapturedPageReference,
} from "../ports/artifacts.js";
import type { SearchQuery } from "../ports/search-reader.js";
import { createSchemaValidator } from "../schema.js";

interface SearchPublishedDocumentsInput extends SearchQuery {
  limit?: number;
  cursor?: string;
}

type PublicationEvent =
  | { type: "ArchivePublicationDecided"; payload: PublicationIdentity }
  | { type: "ArchivePublished"; payload: PublicationIdentity }
  | { type: "ArchiveCompensationDecided"; payload: CompensationDecision }
  | {
      type: "CrawlCompleted";
      payload: {
        archiveId: string;
        manifestDigest: string;
        manifest: ArtifactReference;
      };
    };

interface PageCapturedEvent {
  type: "PageCaptured";
  version: 1;
  messageId: string;
  correlationId: string;
  occurredAt: string;
  payload: CapturedPageReference & {
    finalUrl: string;
    redirectChain: string[];
    urlKey: string;
    warcArtifacts: ArtifactReference[];
  };
}

interface CrawlCompletedEvent {
  archiveId: string;
  manifestDigest: string;
  manifest: ArtifactReference;
}

type PageCapturedResult =
  | {
      status: "COMPLETED";
      outcome: TerminalIndexingOutcome;
    }
  | { status: "BUSY" };

type SnapshotIndexingResult =
  | { outcome: "INDEXED"; snapshotId: string }
  | {
      outcome: "UNSUPPORTED";
      snapshotId: string;
      reasonCode: "UNSUPPORTED_CONTENT_TYPE" | "EMPTY_CONTENT";
    };

interface PublishedSearchResult {
  archiveId: string;
  snapshotId: string;
  url: string;
  capturedAt: string;
  title: string;
  snippet: string;
  score: number;
}

interface ManifestSnapshot {
  snapshotId: string;
  urlKey: string;
  url: string;
  finalUrl: string;
  redirectChain?: string[];
  capturedAt: string;
  warcArtifacts: ArtifactReference[];
}

interface ManifestDocument {
  schemaVersion: 1;
  archiveId: string;
  collectionId?: string;
  createdAt: string;
  snapshots: ManifestSnapshot[];
}

interface PublishedSearchPage {
  results: PublishedSearchResult[];
  nextCursor: string | null;
}

const PageCapturedEventSchema = {
  type: "object",
  properties: {
    type: { type: "string", const: "PageCaptured" },
    version: { type: "integer", const: 1 },
    messageId: { type: "string", minLength: 1 },
    correlationId: { type: "string", minLength: 1 },
    occurredAt: { type: "string", format: "date-time" },
    payload: {
      type: "object",
      properties: {
        archiveId: { type: "string", minLength: 1 },
        snapshotId: { type: "string", minLength: 1 },
        url: { type: "string", minLength: 1 },
        finalUrl: { type: "string", minLength: 1 },
        capturedAt: { type: "string", format: "date-time" },
        contentType: { type: "string", nullable: true },
        urlKey: { type: "string", minLength: 1 },
        redirectChain: {
          type: "array",
          items: { type: "string", minLength: 1 },
        },
        warcArtifacts: {
          type: "array",
          items: ArtifactReferenceSchema,
          minItems: 1,
        },
      },
      required: [
        "archiveId",
        "snapshotId",
        "url",
        "finalUrl",
        "capturedAt",
        "urlKey",
        "redirectChain",
        "warcArtifacts",
      ],
      additionalProperties: false,
    },
  },
  required: [
    "type",
    "version",
    "messageId",
    "correlationId",
    "occurredAt",
    "payload",
  ],
  additionalProperties: false,
} as const;

const pageCapturedEventValidator = createSchemaValidator<PageCapturedEvent>(
  PageCapturedEventSchema,
);

function isPageCapturedEvent(value: unknown): value is PageCapturedEvent {
  return (
    pageCapturedEventValidator.validate(value) &&
    value.payload.archiveId === value.correlationId
  );
}

const ManifestSnapshotSchema = {
  type: "object",
  properties: {
    snapshotId: { type: "string", minLength: 1 },
    urlKey: { type: "string", minLength: 1 },
    url: { type: "string", minLength: 1 },
    finalUrl: { type: "string", minLength: 1 },
    redirectChain: {
      type: "array",
      items: { type: "string", minLength: 1 },
      nullable: true,
    },
    capturedAt: { type: "string", format: "date-time" },
    warcArtifacts: {
      type: "array",
      items: ArtifactReferenceSchema,
      minItems: 1,
    },
  },
  required: [
    "snapshotId",
    "urlKey",
    "url",
    "finalUrl",
    "capturedAt",
    "warcArtifacts",
  ],
  additionalProperties: false,
} as const;

const manifestSnapshotValidator = createSchemaValidator<ManifestSnapshot>(
  ManifestSnapshotSchema,
);

function isManifestSnapshot(value: unknown): value is ManifestSnapshot {
  return manifestSnapshotValidator.validate(value);
}

const ManifestDocumentSchema = {
  type: "object",
  properties: {
    schemaVersion: { type: "integer", const: 1 },
    archiveId: { type: "string", minLength: 1 },
    collectionId: { type: "string", minLength: 1, nullable: true },
    createdAt: { type: "string", format: "date-time" },
    snapshots: {
      type: "array",
      items: ManifestSnapshotSchema,
      minItems: 1,
    },
  },
  required: ["schemaVersion", "archiveId", "createdAt", "snapshots"],
  additionalProperties: false,
} as const;

const manifestDocumentValidator = createSchemaValidator<ManifestDocument>(
  ManifestDocumentSchema,
);

function isManifestDocument(value: unknown): value is ManifestDocument {
  return manifestDocumentValidator.validate(value);
}

export {
  ManifestDocumentSchema,
  ManifestSnapshotSchema,
  PageCapturedEventSchema,
  isPageCapturedEvent,
  isManifestDocument,
  isManifestSnapshot,
};

export type {
  CrawlCompletedEvent,
  ManifestDocument,
  ManifestSnapshot,
  PageCapturedEvent,
  PageCapturedResult,
  PublicationEvent,
  PublishedSearchPage,
  PublishedSearchResult,
  SearchPublishedDocumentsInput,
  SnapshotIndexingResult,
};
