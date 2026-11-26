import type { IndexingCompletion } from "../domain.js";

import type { OutboxEntry } from "./outbox.js";

interface ArchiveManifest {
  archiveId: string;
  manifestDigest: string;
  collectionId: string;
  snapshotIds: readonly string[];
}

interface ManifestLedger {
  get(archiveId: string): Promise<ArchiveManifest | undefined>;

  record(manifest: ArchiveManifest, messageId: string): Promise<void>;

  recordIndexingCompleted(
    completion: IndexingCompletion,
    outboxEntry: OutboxEntry,
  ): Promise<void>;

  contains(
    archiveId: string,
    snapshotId: string,
    collectionId?: string,
  ): Promise<boolean>;
}

export type { ArchiveManifest, ManifestLedger };
