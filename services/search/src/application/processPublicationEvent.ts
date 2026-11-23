import type { PublicationLedger } from "../ports/publication-ledger.js";
import { PublicationEvent } from "./types.js";

type JustPublicationEvents = Exclude<
  PublicationEvent,
  { type: "CrawlCompleted" }
>;

async function processPublicationEvent(
  event: JustPublicationEvents,
  ledger: PublicationLedger,
): Promise<void> {
  switch (event.type) {
    case "ArchivePublicationDecided":
      await ledger.recordPublicationDecision(event.payload);
      return;
    case "ArchivePublished":
      await ledger.recordReplayPublished(event.payload);
      return;
    case "ArchiveCompensationDecided":
      await ledger.recordCompensationDecision(event.payload);
      return;
  }
}

export { processPublicationEvent };

export type { PublicationEvent };
