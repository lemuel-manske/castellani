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
import { isConditionalCheckFailure } from "./error-handling.js";

class DynamoDBPublicationLedger implements PublicationLedger {
  constructor(private readonly client: DynamoDBDocumentClient) {}

  async get(archiveId: string) {
    return getPublicationFacts(this.client, archiveId);
  }

  async recordPublicationDecision(
    identity: PublicationIdentity,
  ): Promise<void> {
    const facts = await this.get(identity.archiveId);

    recordPublicationDecision(facts, identity);

    try {
      await recordPublicationDecisionQuery(this.client, identity);
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
      await recordReplayPublishedQuery(this.client, identity);
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
      await recordCompensationDecisionQuery(this.client, decision);
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

export { DynamoDBPublicationLedger };
