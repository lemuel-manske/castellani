import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import { PublicationConflictError } from "../../../domain/publication.js";
import type { ArchiveManifest, ManifestLedger } from "../../../ports/manifest-ledger.js";
import { getMetadata, getSnapshotDigest, putMetadata, putSnapshot } from "./manifest-ledger-queries.js";

class DynamoDBManifestLedger implements ManifestLedger {
  constructor(private readonly client: DynamoDBDocumentClient, private readonly tableName: string) {
    if (!tableName.trim()) throw new Error("manifest ledger table name must not be empty");
  }

  async record(manifest: ArchiveManifest): Promise<void> {
    if (!manifest.archiveId || !manifest.manifestDigest || new Set(manifest.snapshotIds).size !== manifest.snapshotIds.length || manifest.snapshotIds.some((id) => !id)) {
      throw new Error("invalid archive manifest");
    }
    const existing = await getMetadata(this.client, this.tableName, manifest.archiveId);
    if (existing && (existing.manifestDigest !== manifest.manifestDigest || existing.collectionId !== manifest.collectionId)) {
      throw new PublicationConflictError("archive manifest conflicts with the previously recorded manifest");
    }
    for (const snapshotId of manifest.snapshotIds) {
      await putSnapshot(this.client, this.tableName, manifest, snapshotId);
    }
    await putMetadata(this.client, this.tableName, manifest);
  }

  async contains(archiveId: string, snapshotId: string, collectionId?: string): Promise<boolean> {
    const metadata = await getMetadata(this.client, this.tableName, archiveId);
    if (!metadata || (collectionId !== undefined && metadata.collectionId !== collectionId)) return false;
    return (await getSnapshotDigest(this.client, this.tableName, archiveId, snapshotId)) === metadata.manifestDigest;
  }
}
export { DynamoDBManifestLedger };
