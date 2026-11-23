import { GetCommand, PutCommand } from "@aws-sdk/lib-dynamodb";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import type { ArchiveManifest } from "../../../ports/manifest-ledger.js";
import { MANIFEST_LEDGER } from "./tables.js";

const METADATA_KEY = "!manifest";

async function putSnapshot(
  client: DynamoDBDocumentClient,
  manifest: ArchiveManifest,
  snapshotId: string,
): Promise<void> {
  await client.send(
    new PutCommand({
      TableName: MANIFEST_LEDGER,
      Item: {
        archiveId: manifest.archiveId,
        snapshotId: `snapshot#${snapshotId}`,
        manifestDigest: manifest.manifestDigest,
        collectionId: manifest.collectionId,
      },
      ConditionExpression:
        "attribute_not_exists(manifestDigest) OR (manifestDigest = :digest AND collectionId = :collectionId)",
      ExpressionAttributeValues: {
        ":digest": manifest.manifestDigest,
        ":collectionId": manifest.collectionId,
      },
    }),
  );
}

async function putMetadata(
  client: DynamoDBDocumentClient,
  manifest: ArchiveManifest,
): Promise<void> {
  await client.send(
    new PutCommand({
      TableName: MANIFEST_LEDGER,
      Item: {
        archiveId: manifest.archiveId,
        snapshotId: METADATA_KEY,
        manifestDigest: manifest.manifestDigest,
        collectionId: manifest.collectionId,
        snapshotCount: manifest.snapshotIds.length,
        complete: true,
      },
      ConditionExpression:
        "attribute_not_exists(manifestDigest) OR (manifestDigest = :digest AND collectionId = :collectionId AND snapshotCount = :count)",
      ExpressionAttributeValues: {
        ":digest": manifest.manifestDigest,
        ":collectionId": manifest.collectionId,
        ":count": manifest.snapshotIds.length,
      },
    }),
  );
}

async function getMetadata(
  client: DynamoDBDocumentClient,
  archiveId: string,
): Promise<{ manifestDigest: string; collectionId: string } | null> {
  const response = await client.send(
    new GetCommand({
      TableName: MANIFEST_LEDGER,
      Key: { archiveId, snapshotId: METADATA_KEY },
      ConsistentRead: true,
    }),
  );
  const item = response.Item;

  return item?.complete === true &&
    typeof item.manifestDigest === "string" &&
    typeof item.collectionId === "string"
    ? { manifestDigest: item.manifestDigest, collectionId: item.collectionId }
    : null;
}

async function getSnapshotDigest(
  client: DynamoDBDocumentClient,
  archiveId: string,
  snapshotId: string,
): Promise<string | null> {
  const response = await client.send(
    new GetCommand({
      TableName: MANIFEST_LEDGER,
      Key: { archiveId, snapshotId: `snapshot#${snapshotId}` },
      ConsistentRead: true,
    }),
  );

  return typeof response.Item?.manifestDigest === "string"
    ? response.Item.manifestDigest
    : null;
}

export { getMetadata, getSnapshotDigest, putMetadata, putSnapshot };
