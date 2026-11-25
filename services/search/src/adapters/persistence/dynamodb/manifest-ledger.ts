import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import { PublicationConflictError } from "../../../domain/publication.js";
import type {
  ArchiveManifest,
  ManifestLedger,
} from "../../../ports/manifest-ledger.js";
import {
  getMetadata,
  getSnapshotDigest,
  putMetadata,
  putSnapshot,
} from "./manifest-ledger-queries.js";
import { isConditionalCheckFailure } from "./error-handling.js";

class DynamoDBManifestLedger implements ManifestLedger {
  constructor(private readonly client: DynamoDBDocumentClient) {}

  async record(manifest: ArchiveManifest, messageId: string): Promise<void> {
    if (
      !manifest.archiveId ||
      !manifest.manifestDigest ||
      new Set(manifest.snapshotIds).size !== manifest.snapshotIds.length ||
      manifest.snapshotIds.some((id) => !id)
    ) {
      throw new Error("invalid archive manifest");
    }

    const existing = await getMetadata(this.client, manifest.archiveId);

    if (
      existing &&
      (existing.manifestDigest !== manifest.manifestDigest ||
        existing.collectionId !== manifest.collectionId)
    ) {
      throw new PublicationConflictError(
        "archive manifest conflicts with the previously recorded manifest",
      );
    }

    for (const snapshotId of manifest.snapshotIds) {
      await putSnapshot(this.client, manifest, snapshotId);
    }

    try {
      await putMetadata(this.client, manifest, messageId);
    } catch (error) {
      if (!isConditionalCheckFailure(error)) {
        throw error;
      }

      const metadata = await getMetadata(this.client, manifest.archiveId);

      if (
        metadata?.manifestDigest !== manifest.manifestDigest ||
        metadata.collectionId !== manifest.collectionId ||
        metadata.snapshotCount !== manifest.snapshotIds.length ||
        !metadata.processedMessageIds?.includes(messageId)
      ) {
        throw new PublicationConflictError(
          "archive manifest changed concurrently; retry the operation",
        );
      }
    }
  }

  async contains(
    archiveId: string,
    snapshotId: string,
    collectionId?: string,
  ): Promise<boolean> {
    const metadata = await getMetadata(this.client, archiveId);

    if (
      !metadata ||
      (collectionId !== undefined && metadata.collectionId !== collectionId)
    )
      return false;

    return (
      (await getSnapshotDigest(this.client, archiveId, snapshotId)) ===
      metadata.manifestDigest
    );
  }
}
export { DynamoDBManifestLedger };
