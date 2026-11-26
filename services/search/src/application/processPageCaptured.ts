import {
  INDEXING_CLAIM_STATUS,
  INDEXING_OUTCOME,
  PAGE_CAPTURE_STATUS,
} from "../domain/index.js";
import type { CapturedPageReader } from "../ports/artifacts.js";
import type { IndexingLedger } from "../ports/indexing-ledger.js";
import type { PublicationLedger } from "../ports/publication-ledger.js";
import type { SearchDocumentWriter } from "../ports/search-index.js";

import { indexCapturedPage } from "./indexCapturedPage.js";

import { PageCapturedEvent, PageCapturedResult } from "./types.js";

async function processPageCaptured(
  event: PageCapturedEvent,
  ledger: IndexingLedger,
  capturedPageReader: CapturedPageReader,
  documentWriter: SearchDocumentWriter,
  leaseDurationSeconds: number,
  maxAttempts: number,
  publicationLedger: PublicationLedger,
): Promise<PageCapturedResult> {
  const facts = await publicationLedger.get(event.payload.archiveId);

  if (facts.compensationDecision !== null) {
    return {
      status: PAGE_CAPTURE_STATUS.COMPLETED,
      outcome: INDEXING_OUTCOME.UNSUPPORTED,
    };
  }

  const claimResult = await ledger.claim(
    event.payload.archiveId,
    event.payload.snapshotId,
    event.messageId,
    leaseDurationSeconds,
    maxAttempts,
  );

  if (claimResult.status === INDEXING_CLAIM_STATUS.BUSY) {
    return { status: PAGE_CAPTURE_STATUS.BUSY };
  }

  if (claimResult.status === INDEXING_CLAIM_STATUS.TERMINAL) {
    return {
      status: PAGE_CAPTURE_STATUS.COMPLETED,
      outcome: claimResult.outcome,
    };
  }

  try {
    const result = await indexCapturedPage(
      event.payload,
      event.payload.warcArtifacts,
      capturedPageReader,
      documentWriter,
    );

    await ledger.complete(
      claimResult.claim,
      result.outcome,
      result.outcome === INDEXING_OUTCOME.UNSUPPORTED
        ? result.reasonCode
        : undefined,
    );

    return { status: PAGE_CAPTURE_STATUS.COMPLETED, outcome: result.outcome };
  } catch (error) {
    const reason =
      error instanceof Error ? error.message : "unknown indexing error";

    await ledger.release(claimResult.claim, reason);

    throw error;
  }
}

export { processPageCaptured };
