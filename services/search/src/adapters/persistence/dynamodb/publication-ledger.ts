import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import type {
  CompensationDecision,
  PublicationIdentity,
} from "../../../domain.js";
import {
  PublicationConflictError,
  recordCompensationDecision,
  recordPublicationDecision,
  recordReplayPublished,
} from "../../../domain/publication.js";
import type { PublicationLedger } from "../../../ports/publication-ledger.js";
import {
  getPublicationFacts,
  recordCompensationDecisionQuery,
  recordPublicationDecisionQuery,
  recordReplayPublishedQuery,
} from "./publication-ledger-queries.js";

class DynamoDBPublicationLedger implements PublicationLedger {
  constructor(
    private readonly client: DynamoDBDocumentClient,
    private readonly tableName: string,
  ) {
    if (!tableName.trim()) {
      throw new Error("publication ledger table name must not be empty");
    }
  }

  async get(archiveId: string) {
    if (!archiveId) {
      throw new Error("archiveId must not be empty");
    }

    return getPublicationFacts(this.client, this.tableName, archiveId);
  }

  async recordPublicationDecision(
    identity: PublicationIdentity,
  ): Promise<void> {
    const facts = await this.get(identity.archiveId);

    recordPublicationDecision(facts, identity);

    try {
      await recordPublicationDecisionQuery(
        this.client,
        this.tableName,
        identity,
      );
    } catch (error) {
      if (!isConditionalCheckFailure(error)) {
        throw error;
      }

      const current = await this.get(identity.archiveId);

      if (recordPublicationDecision(current, identity) === current) {
        return;
      }

      throw new PublicationConflictError(
        "publication state changed concurrently; retry the operation",
      );
    }
  }

  async recordReplayPublished(identity: PublicationIdentity): Promise<void> {
    const facts = await this.get(identity.archiveId);

    recordReplayPublished(facts, identity);

    try {
      await recordReplayPublishedQuery(this.client, this.tableName, identity);
    } catch (error) {
      if (!isConditionalCheckFailure(error)) {
        throw error;
      }

      const current = await this.get(identity.archiveId);

      if (recordReplayPublished(current, identity) === current) {
        return;
      }

      throw new PublicationConflictError(
        "publication state changed concurrently; retry the operation",
      );
    }
  }

  async recordCompensationDecision(
    decision: CompensationDecision,
  ): Promise<void> {
    const facts = await this.get(decision.archiveId);

    recordCompensationDecision(facts, decision);

    try {
      await recordCompensationDecisionQuery(
        this.client,
        this.tableName,
        decision,
      );
    } catch (error) {
      if (!isConditionalCheckFailure(error)) {
        throw error;
      }

      const current = await this.get(decision.archiveId);

      if (recordCompensationDecision(current, decision) === current) {
        return;
      }

      throw new PublicationConflictError(
        "publication state changed concurrently; retry the operation",
      );
    }
  }
}

function isConditionalCheckFailure(error: unknown): boolean {
  return (
    error instanceof Error && error.name === "ConditionalCheckFailedException"
  );
}

export { DynamoDBPublicationLedger };
