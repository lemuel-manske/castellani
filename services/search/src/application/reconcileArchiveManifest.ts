import type { ManifestReconciliation, ManifestSnapshot } from "../domain.js";
import { reconcileManifest } from "../domain/indexing.js";

import type { IndexingLedger } from "../ports/indexing-ledger.js";

async function reconcileArchiveManifest(
  archiveId: string,
  snapshots: readonly ManifestSnapshot[],
  ledger: IndexingLedger,
): Promise<ManifestReconciliation> {
  if (!archiveId) {
    throw new Error("archiveId must not be empty");
  }

  const entries = await ledger.listByArchive(archiveId);

  return reconcileManifest(snapshots, entries);
}

export { reconcileArchiveManifest };
