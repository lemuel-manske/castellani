import { GetCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import type {
  CompensationDecision,
  PublicationFacts,
  PublicationIdentity,
} from "../../../domain.js";
import { emptyPublicationFacts } from "../../../domain/publication.js";

interface PublicationLedgerItem {
  publicationDecision?: string;
  replayPublication?: string;
  compensationDecision?: string;
}

async function getPublicationFacts(
  client: DynamoDBDocumentClient,
  tableName: string,
  archiveId: string,
): Promise<PublicationFacts> {
  const response = await client.send(
    new GetCommand({
      TableName: tableName,
      Key: { archiveId },
      ConsistentRead: true,
    }),
  );

  return factsFromItem(response.Item as PublicationLedgerItem | undefined);
}

async function recordPublicationDecisionQuery(
  client: DynamoDBDocumentClient,
  tableName: string,
  identity: PublicationIdentity,
): Promise<void> {
  await client.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { archiveId: identity.archiveId },
      UpdateExpression: "SET #publication = :identity",
      ConditionExpression:
        "attribute_not_exists(#compensation) AND (attribute_not_exists(#replay) OR #replay = :identity) AND (attribute_not_exists(#publication) OR #publication = :identity)",
      ExpressionAttributeNames: {
        "#publication": "publicationDecision",
        "#replay": "replayPublication",
        "#compensation": "compensationDecision",
      },
      ExpressionAttributeValues: { ":identity": serializeFact(identity) },
    }),
  );
}

async function recordReplayPublishedQuery(
  client: DynamoDBDocumentClient,
  tableName: string,
  identity: PublicationIdentity,
): Promise<void> {
  await client.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { archiveId: identity.archiveId },
      UpdateExpression: "SET #replay = :identity",
      ConditionExpression:
        "attribute_not_exists(#compensation) AND (attribute_not_exists(#publication) OR #publication = :identity) AND (attribute_not_exists(#replay) OR #replay = :identity)",
      ExpressionAttributeNames: {
        "#publication": "publicationDecision",
        "#replay": "replayPublication",
        "#compensation": "compensationDecision",
      },
      ExpressionAttributeValues: { ":identity": serializeFact(identity) },
    }),
  );
}

async function recordCompensationDecisionQuery(
  client: DynamoDBDocumentClient,
  tableName: string,
  decision: CompensationDecision,
): Promise<void> {
  await client.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { archiveId: decision.archiveId },
      UpdateExpression: "SET #compensation = :identity",
      ConditionExpression:
        "attribute_not_exists(#publication) AND attribute_not_exists(#replay) AND (attribute_not_exists(#compensation) OR #compensation = :identity)",
      ExpressionAttributeNames: {
        "#publication": "publicationDecision",
        "#replay": "replayPublication",
        "#compensation": "compensationDecision",
      },
      ExpressionAttributeValues: { ":identity": serializeFact(decision) },
    }),
  );
}

function factsFromItem(
  item: PublicationLedgerItem | undefined,
): PublicationFacts {
  if (!item) {
    return emptyPublicationFacts();
  }

  return {
    publicationDecision: parseFact<PublicationIdentity>(
      item.publicationDecision,
      "publicationDecision",
    ),
    replayPublication: parseFact<PublicationIdentity>(
      item.replayPublication,
      "replayPublication",
    ),
    compensationDecision: parseFact<CompensationDecision>(
      item.compensationDecision,
      "compensationDecision",
    ),
  };
}

function serializeFact(
  value: PublicationIdentity | CompensationDecision,
): string {
  return "packageDigest" in value
    ? JSON.stringify({
        archiveId: value.archiveId,
        decisionVersion: value.decisionVersion,
        packageDigest: value.packageDigest,
      })
    : JSON.stringify({
        archiveId: value.archiveId,
        decisionVersion: value.decisionVersion,
        reasonCode: value.reasonCode,
      });
}

function parseFact<T>(value: string | undefined, name: string): T | null {
  if (value === undefined) {
    return null;
  }

  try {
    return JSON.parse(value) as T;
  } catch {
    throw new Error(`corrupt publication ledger attribute: ${name}`);
  }
}

export {
  getPublicationFacts,
  recordCompensationDecisionQuery,
  recordPublicationDecisionQuery,
  recordReplayPublishedQuery,
};
