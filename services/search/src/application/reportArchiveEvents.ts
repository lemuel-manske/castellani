import type { IndexingCompletion, SearchReadiness } from "../domain.js";
import { isPublicationAuthorized } from "../domain/publication.js";

import type { IndexingLedger } from "../ports/indexing-ledger.js";
import type { ManifestLedger } from "../ports/manifest-ledger.js";
import type { PublicationLedger } from "../ports/publication-ledger.js";

import { reconcileArchiveManifest } from "./reconcileArchiveManifest.js";
import {
  createSearchIndexingCompletedOutboxEntry,
  createSearchReadyOutboxEntry,
} from "./searchEvents.js";

/** Reports aggregate indexing completion and authorized search readiness. */
async function reportArchiveEvents(
  archiveId: string,
  indexingLedger: IndexingLedger,
  manifestLedger: ManifestLedger,
  publicationLedger: PublicationLedger,
): Promise<void> {
  const facts = await publicationLedger.get(archiveId);

  if (facts.compensationDecision !== null) {
    return;
  }

  const manifest = await manifestLedger.get(archiveId);

  if (manifest === undefined) {
    return;
  }

  const reconciliation = await reconcileArchiveManifest(
    archiveId,
    manifest.snapshotIds.map((snapshotId) => ({ snapshotId })),
    indexingLedger,
  );

  if (!reconciliation.complete) {
    return;
  }

  const completion: IndexingCompletion = {
    archiveId,
    manifestDigest: manifest.manifestDigest,
    expected: reconciliation.expectedCount,
    indexed: reconciliation.indexedCount,
    failed: reconciliation.failedCount,
    unsupported: reconciliation.unsupportedCount,
  };

  await manifestLedger.recordIndexingCompleted(
    completion,
    createSearchIndexingCompletedOutboxEntry(completion),
  );

  if (!isPublicationAuthorized(facts) || facts.publicationDecision === null) {
    return;
  }

  const readiness: SearchReadiness = {
    archiveId,
    decisionVersion: facts.publicationDecision.decisionVersion,
    manifestDigest: manifest.manifestDigest,
  };

  await publicationLedger.recordSearchReady(
    readiness,
    createSearchReadyOutboxEntry(readiness),
  );
}

export { reportArchiveEvents };
