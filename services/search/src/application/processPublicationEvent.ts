import type { CompensationDecision, PublicationIdentity } from "../domain.js";
import type { ArtifactReference } from "../ports/artifacts.js";
import type { PublicationLedger } from "../ports/publication-ledger.js";

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

async function processPublicationEvent(
  event: Exclude<PublicationEvent, { type: "CrawlCompleted" }>,
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
