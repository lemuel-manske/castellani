import { GetCommand, PutCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import type { ArchiveManifest } from "../../../ports/manifest-ledger.js";
import { MANIFEST_LEDGER } from "./tables.js";

const METADATA_KEY = "!manifest";

interface ManifestMetadata {
  manifestDigest: string;
  collectionId: string;
  snapshotCount: number;
  processedMessageIds?: string[];
}

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
  messageId: string,
): Promise<void> {
  await client.send(
    new UpdateCommand({
      TableName: MANIFEST_LEDGER,
      Key: { archiveId: manifest.archiveId, snapshotId: METADATA_KEY },
      UpdateExpression:
        "SET #digest = :digest, #collection = :collectionId, #count = :count, #complete = :complete, #processed = list_append(if_not_exists(#processed, :empty), :messages)",
      ConditionExpression:
        "(attribute_not_exists(#digest) OR (#digest = :digest AND #collection = :collectionId AND #count = :count)) AND (attribute_not_exists(#processed) OR NOT contains(#processed, :message))",
      ExpressionAttributeNames: {
        "#digest": "manifestDigest",
        "#collection": "collectionId",
        "#count": "snapshotCount",
        "#complete": "complete",
        "#processed": "processedMessageIds",
      },
      ExpressionAttributeValues: {
        ":digest": manifest.manifestDigest,
        ":collectionId": manifest.collectionId,
        ":count": manifest.snapshotIds.length,
        ":complete": true,
        ":empty": [],
        ":messages": [messageId],
        ":message": messageId,
      },
    }),
  );
}

async function getMetadata(
  client: DynamoDBDocumentClient,
  archiveId: string,
): Promise<ManifestMetadata | null> {
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
    typeof item.collectionId === "string" &&
    typeof item.snapshotCount === "number"
    ? {
        manifestDigest: item.manifestDigest,
        collectionId: item.collectionId,
        snapshotCount: item.snapshotCount,
        processedMessageIds: item.processedMessageIds as string[] | undefined,
      }
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
