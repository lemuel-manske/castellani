import {
  ARCHIVE_COMPENSATION_DECIDED_EVENT,
  ARCHIVE_PUBLICATION_DECIDED_EVENT,
  ARCHIVE_PUBLISHED_EVENT,
  CRAWL_COMPLETED_EVENT,
  CONTENT_REASON_CODE,
  INDEXING_OUTCOME,
  PAGE_CAPTURE_STATUS,
  PAGE_CAPTURED_EVENT,
  type CompensationDecision,
  type CompletionCrawl,
  type PublicationIdentity,
  type TerminalIndexingOutcome,
} from "../domain/index.js";

import type {
  ArtifactReference,
  CapturedPageReference,
} from "../ports/artifacts.js";
import type { SearchQuery } from "../ports/search-reader.js";

interface SearchPublishedDocumentsInput extends SearchQuery {
  limit?: number;
  cursor?: string;
}

type Event<Type extends string, Payload> = {
  type: Type;
  version: 1;
  messageId: string;
  correlationId: string;
  occurredAt: string;
  payload: Payload;
};

type PublicationEvent =
  | Event<typeof ARCHIVE_PUBLICATION_DECIDED_EVENT, PublicationIdentity>
  | Event<typeof ARCHIVE_PUBLISHED_EVENT, PublicationIdentity>
  | Event<typeof ARCHIVE_COMPENSATION_DECIDED_EVENT, CompensationDecision>
  | Event<typeof CRAWL_COMPLETED_EVENT, CompletionCrawl>;

type PageCapturedEvent = Event<
  typeof PAGE_CAPTURED_EVENT,
  CapturedPageReference & {
    redirectChain?: string[];
    urlKey: string;
    warcArtifacts: ArtifactReference[];
  }
>;

type PageCapturedResult =
  | {
      status: typeof PAGE_CAPTURE_STATUS.COMPLETED;
      outcome: TerminalIndexingOutcome;
    }
  | { status: typeof PAGE_CAPTURE_STATUS.BUSY };

type SnapshotIndexingResult =
  | {
      outcome: typeof INDEXING_OUTCOME.INDEXED;
      snapshotId: string;
    }
  | {
      outcome: typeof INDEXING_OUTCOME.UNSUPPORTED;
      snapshotId: string;
      reasonCode: (typeof CONTENT_REASON_CODE)[keyof typeof CONTENT_REASON_CODE];
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
  minDepth?: number;
  contentType?: string;
  capturedAt: string;
  warcArtifacts: ArtifactReference[];
}

interface ManifestDocument {
  schemaVersion: 1;
  archiveId: string;
  collectionId?: string;
  normalizerVersion: string;
  seedUrl: string;
  createdAt: string;
  snapshots: ManifestSnapshot[];
  failedPages: { urlKey: string; reasonCode: string }[];
}

interface PublishedSearchPage {
  results: PublishedSearchResult[];
  nextCursor: string | null;
}

export type {
  Event,
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
