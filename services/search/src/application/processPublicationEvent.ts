import {
  ARCHIVE_COMPENSATION_DECIDED_EVENT,
  ARCHIVE_PUBLICATION_DECIDED_EVENT,
  ARCHIVE_PUBLISHED_EVENT,
  CRAWL_COMPLETED_EVENT,
} from "../domain/index.js";

import type { PublicationLedger } from "../ports/publication-ledger.js";
import type { SearchDocumentWriter } from "../ports/search-index.js";

import { createSearchCompensatedOutboxEntry } from "./searchCompensation.js";

import { PublicationEvent } from "./types.js";

type JustPublicationEvents = Exclude<
  PublicationEvent,
  { type: typeof CRAWL_COMPLETED_EVENT }
>;

async function processPublicationEvent(
  event: JustPublicationEvents,
  ledger: PublicationLedger,
  documentWriter: SearchDocumentWriter,
): Promise<void> {
  switch (event.type) {
    case ARCHIVE_PUBLICATION_DECIDED_EVENT:
      await ledger.recordPublicationDecision(event.payload, event.messageId);
      return;
    case ARCHIVE_PUBLISHED_EVENT:
      await ledger.recordReplayPublished(event.payload, event.messageId);
      return;
    case ARCHIVE_COMPENSATION_DECIDED_EVENT:
      await ledger.recordCompensationDecision(
        event.payload,
        event.messageId,
        createSearchCompensatedOutboxEntry(event.payload),
      );

      await documentWriter.deleteArchive(event.payload.archiveId);
      return;
  }
}

export { processPublicationEvent };

export type { PublicationEvent };
