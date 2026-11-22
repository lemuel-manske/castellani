import type { IndexingOutcome } from "../domain.js";
import type { ArtifactReference } from "../ports/artifacts.js";
import type { IndexingLedger } from "../ports/indexing-ledger.js";
import type { SearchDocumentWriter } from "../ports/search-index.js";
import type { CapturedPageReader, CapturedPageReference } from "../ports/artifacts.js";
import { indexCapturedPage } from "./indexCapturedPage.js";

interface PageCapturedEvent {
  messageId: string;
  correlationId: string;
  occurredAt: string;
  payload: CapturedPageReference & {
    urlKey: string;
    warcArtifacts: ArtifactReference[];
  };
}

type PageCapturedResult =
  | { status: "COMPLETED"; outcome: Extract<IndexingOutcome, "INDEXED" | "UNSUPPORTED"> }
  | { status: "BUSY" }
  | { status: "DUPLICATE"; outcome: Extract<IndexingOutcome, "INDEXED" | "UNSUPPORTED" | "FAILED"> };

interface ProcessPageCapturedDependencies {
  ledger: IndexingLedger;
  capturedPageReader: CapturedPageReader;
  documentWriter: SearchDocumentWriter;
  leaseDurationSeconds?: number;
}

async function processPageCaptured(
  event: PageCapturedEvent,
  dependencies: ProcessPageCapturedDependencies,
): Promise<PageCapturedResult> {
  const claimResult = await dependencies.ledger.claim(
    event.payload.archiveId,
    event.payload.snapshotId,
    event.messageId,
    dependencies.leaseDurationSeconds ?? 120,
  );

  if (claimResult.status === "BUSY") {
    return { status: "BUSY" };
  }

  if (claimResult.status === "TERMINAL") {
    return { status: "DUPLICATE", outcome: claimResult.outcome };
  }

  try {
    const result = await indexCapturedPage(
      event.payload,
      event.payload.warcArtifacts,
      dependencies.capturedPageReader,
      dependencies.documentWriter,
    );

    await dependencies.ledger.complete(
      claimResult.claim,
      result.outcome,
      result.outcome === "UNSUPPORTED" ? result.reasonCode : undefined,
    );

    return { status: "COMPLETED", outcome: result.outcome };
  } catch (error) {
    const reason = error instanceof Error ? error.message : "unknown indexing error";
    await dependencies.ledger.release(claimResult.claim, reason);
    throw error;
  }
}

export { processPageCaptured };
export type { PageCapturedEvent, PageCapturedResult, ProcessPageCapturedDependencies };
