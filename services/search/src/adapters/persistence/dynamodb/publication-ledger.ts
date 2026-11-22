import {
  GetCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import type {
  CompensationDecision,
  PublicationFacts,
  PublicationIdentity,
} from "../../../domain.js";
import {
  PublicationConflictError,
  emptyPublicationFacts,
  recordCompensationDecision,
  recordPublicationDecision,
  recordReplayPublished,
} from "../../../domain/publication.js";
import type { PublicationLedger } from "../../../ports/publication-ledger.js";

interface PublicationLedgerItem {
  publicationDecision?: string;
  replayPublication?: string;
  compensationDecision?: string;
}

class DynamoDBPublicationLedger implements PublicationLedger {
  constructor(
    private readonly client: DynamoDBDocumentClient,
    private readonly tableName: string,
  ) {
    if (!tableName.trim()) {
      throw new Error("publication ledger table name must not be empty");
    }
  }

  async get(archiveId: string): Promise<PublicationFacts> {
    if (!archiveId) {
      throw new Error("archiveId must not be empty");
    }

    const response = await this.client.send(
      new GetCommand({
        TableName: this.tableName,
        Key: { archiveId },
        ConsistentRead: true,
      }),
    );

    return factsFromItem(response.Item as PublicationLedgerItem | undefined);
  }

  async recordPublicationDecision(identity: PublicationIdentity): Promise<void> {
    const facts = await this.get(identity.archiveId);
    recordPublicationDecision(facts, identity);

    await this.update(
      identity.archiveId,
      "publicationDecision",
      identity,
      "attribute_not_exists(#compensation) AND (attribute_not_exists(#replay) OR #replay = :identity) AND (attribute_not_exists(#publication) OR #publication = :identity)",
    );
  }

  async recordReplayPublished(identity: PublicationIdentity): Promise<void> {
    const facts = await this.get(identity.archiveId);
    recordReplayPublished(facts, identity);

    await this.update(
      identity.archiveId,
      "replayPublication",
      identity,
      "attribute_not_exists(#compensation) AND (attribute_not_exists(#publication) OR #publication = :identity) AND (attribute_not_exists(#replay) OR #replay = :identity)",
    );
  }

  async recordCompensationDecision(
    decision: CompensationDecision,
  ): Promise<void> {
    const facts = await this.get(decision.archiveId);
    recordCompensationDecision(facts, decision);

    await this.update(
      decision.archiveId,
      "compensationDecision",
      decision,
      "attribute_not_exists(#publication) AND attribute_not_exists(#replay) AND (attribute_not_exists(#compensation) OR #compensation = :identity)",
    );
  }

  private async update(
    archiveId: string,
    attribute: keyof PublicationLedgerItem,
    value: PublicationIdentity | CompensationDecision,
    condition: string,
  ): Promise<void> {
    const serialized = serializeFact(value);

    try {
      await this.client.send(
        new UpdateCommand({
          TableName: this.tableName,
          Key: { archiveId },
          UpdateExpression: "SET #fact = :identity",
          ConditionExpression: condition,
          ExpressionAttributeNames: {
            "#fact": attribute,
            "#publication": "publicationDecision",
            "#replay": "replayPublication",
            "#compensation": "compensationDecision",
          },
          ExpressionAttributeValues: { ":identity": serialized },
        }),
      );
    } catch (error) {
      if (
        !(error instanceof Error) ||
        error.name !== "ConditionalCheckFailedException"
      ) {
        throw error;
      }

      const current = await this.get(archiveId);

      if (attribute === "publicationDecision") {
        recordPublicationDecision(current, value as PublicationIdentity);
      } else if (attribute === "replayPublication") {
        recordReplayPublished(current, value as PublicationIdentity);
      } else {
        recordCompensationDecision(current, value as CompensationDecision);
      }

      throw new PublicationConflictError(
        "publication state changed concurrently; retry the operation",
      );
    }
  }
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

export { DynamoDBPublicationLedger };
