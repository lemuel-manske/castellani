import {
  GetCommand,
  TransactWriteCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";

import type {
  CompensationDecision,
  PublicationFacts,
  PublicationIdentity,
  SearchReadiness,
} from "../../../domain.js";
import {
  emptyPublicationFacts,
  isPublicationAuthorized,
  PublicationConflictError,
} from "../../../domain/publication.js";

import type { OutboxEntry } from "../../../ports/outbox.js";

import { putOutboxEntry } from "./outbox-queries.js";
import { PUBLICATION_LEDGER } from "./tables.js";

interface PublicationLedgerItem {
  publicationDecision?: string;
  replayPublication?: string;
  compensationDecision?: string;
  searchReady?: string;
  processedMessageIds?: string[];
}

async function getPublicationEntry(
  client: DynamoDBDocumentClient,
  archiveId: string,
): Promise<PublicationLedgerItem | undefined> {
  const response = await client.send(
    new GetCommand({
      TableName: PUBLICATION_LEDGER,
      Key: { archiveId },
      ConsistentRead: true,
    }),
  );

  return response.Item as PublicationLedgerItem | undefined;
}

async function getPublicationFacts(
  client: DynamoDBDocumentClient,
  archiveId: string,
): Promise<PublicationFacts> {
  return factsFromItem(await getPublicationEntry(client, archiveId));
}

async function recordPublicationDecisionQuery(
  client: DynamoDBDocumentClient,
  identity: PublicationIdentity,
  messageId: string,
): Promise<void> {
  await client.send(
    new UpdateCommand({
      TableName: PUBLICATION_LEDGER,
      Key: { archiveId: identity.archiveId },
      UpdateExpression:
        "SET #publication = :identity, #processed = list_append(if_not_exists(#processed, :empty), :messages)",
      ConditionExpression:
        "attribute_not_exists(#compensation) AND (attribute_not_exists(#replay) OR #replay = :identity) AND (attribute_not_exists(#publication) OR #publication = :identity) AND (attribute_not_exists(#processed) OR NOT contains(#processed, :message))",
      ExpressionAttributeNames: {
        "#publication": "publicationDecision",
        "#replay": "replayPublication",
        "#compensation": "compensationDecision",
        "#processed": "processedMessageIds",
      },
      ExpressionAttributeValues: {
        ":identity": serializeFact(identity),
        ":empty": [],
        ":messages": [messageId],
        ":message": messageId,
      },
    }),
  );
}

async function recordReplayPublishedQuery(
  client: DynamoDBDocumentClient,
  identity: PublicationIdentity,
  messageId: string,
): Promise<void> {
  await client.send(
    new UpdateCommand({
      TableName: PUBLICATION_LEDGER,
      Key: { archiveId: identity.archiveId },
      UpdateExpression:
        "SET #replay = :identity, #processed = list_append(if_not_exists(#processed, :empty), :messages)",
      ConditionExpression:
        "attribute_not_exists(#compensation) AND (attribute_not_exists(#publication) OR #publication = :identity) AND (attribute_not_exists(#replay) OR #replay = :identity) AND (attribute_not_exists(#processed) OR NOT contains(#processed, :message))",
      ExpressionAttributeNames: {
        "#publication": "publicationDecision",
        "#replay": "replayPublication",
        "#compensation": "compensationDecision",
        "#processed": "processedMessageIds",
      },
      ExpressionAttributeValues: {
        ":identity": serializeFact(identity),
        ":empty": [],
        ":messages": [messageId],
        ":message": messageId,
      },
    }),
  );
}

async function recordCompensationDecisionTransaction(
  client: DynamoDBDocumentClient,
  decision: CompensationDecision,
  messageId: string,
  outboxEntry: OutboxEntry,
): Promise<void> {
  await client.send(
    new TransactWriteCommand({
      TransactItems: [
        {
          Update: {
            TableName: PUBLICATION_LEDGER,
            Key: { archiveId: decision.archiveId },
            UpdateExpression:
              "SET #compensation = :identity, #processed = list_append(if_not_exists(#processed, :empty), :messages)",
            ConditionExpression:
              "attribute_not_exists(#publication) AND attribute_not_exists(#replay) AND (attribute_not_exists(#compensation) OR #compensation = :identity) AND (attribute_not_exists(#processed) OR NOT contains(#processed, :message))",
            ExpressionAttributeNames: {
              "#publication": "publicationDecision",
              "#replay": "replayPublication",
              "#compensation": "compensationDecision",
              "#processed": "processedMessageIds",
            },
            ExpressionAttributeValues: {
              ":identity": serializeFact(decision),
              ":empty": [],
              ":messages": [messageId],
              ":message": messageId,
            },
          },
        },
        putOutboxEntry(outboxEntry),
      ],
    }),
  );
}

async function recordSearchReadyTransaction(
  client: DynamoDBDocumentClient,
  readiness: SearchReadiness,
  item: PublicationLedgerItem,
  outboxEntry: OutboxEntry,
): Promise<void> {
  const facts = factsFromItem(item);
  const decision = facts.publicationDecision;

  if (
    !isPublicationAuthorized(facts) ||
    decision === null ||
    decision.archiveId !== readiness.archiveId ||
    decision.decisionVersion !== readiness.decisionVersion ||
    item.publicationDecision === undefined ||
    item.replayPublication === undefined
  ) {
    throw new PublicationConflictError(
      "search readiness does not match authorized publication facts",
    );
  }

  await client.send(
    new TransactWriteCommand({
      TransactItems: [
        {
          Update: {
            TableName: PUBLICATION_LEDGER,
            Key: { archiveId: readiness.archiveId },
            UpdateExpression: "SET #ready = :readiness",
            ConditionExpression:
              "attribute_not_exists(#compensation) AND #publication = :publication AND #replay = :replay AND attribute_not_exists(#ready)",
            ExpressionAttributeNames: {
              "#compensation": "compensationDecision",
              "#publication": "publicationDecision",
              "#replay": "replayPublication",
              "#ready": "searchReady",
            },
            ExpressionAttributeValues: {
              ":publication": item.publicationDecision,
              ":replay": item.replayPublication,
              ":readiness": JSON.stringify(readiness),
            },
          },
        },
        putOutboxEntry(outboxEntry),
      ],
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
    publicationDecision: parseFact(
      item.publicationDecision,
      "publicationDecision",
    ) as PublicationIdentity | null,
    replayPublication: parseFact(
      item.replayPublication,
      "replayPublication",
    ) as PublicationIdentity | null,
    compensationDecision: parseFact(
      item.compensationDecision,
      "compensationDecision",
    ) as CompensationDecision | null,
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

function parseFact(value: string | undefined, name: string): unknown {
  if (value === undefined) {
    return null;
  }

  try {
    return JSON.parse(value) as unknown;
  } catch {
    throw new Error(`corrupt publication ledger attribute: ${name}`);
  }
}

export {
  getPublicationEntry,
  getPublicationFacts,
  recordCompensationDecisionTransaction,
  recordPublicationDecisionQuery,
  recordReplayPublishedQuery,
  recordSearchReadyTransaction,
};
