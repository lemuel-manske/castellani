interface ArchiveManifest {
  archiveId: string;
  manifestDigest: string;
  collectionId: string;
  snapshotIds: readonly string[];
}

interface ManifestLedger {
  record(manifest: ArchiveManifest): Promise<void>;

  contains(
    archiveId: string,
    snapshotId: string,
    collectionId?: string,
  ): Promise<boolean>;
}

export type { ArchiveManifest, ManifestLedger };
