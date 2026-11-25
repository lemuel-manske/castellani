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
import type { Outbox, OutboxEntry } from "../../../ports/outbox.js";
import type { PublicationLedger } from "../../../ports/publication-ledger.js";
import {
  getPublicationFacts,
  recordCompensationDecisionTransaction,
  recordPublicationDecisionQuery,
  recordReplayPublishedQuery,
} from "./publication-ledger-queries.js";
import { isConditionalCheckFailure } from "./error-handling.js";

class DynamoDBPublicationLedger implements PublicationLedger {
  constructor(
    private readonly client: DynamoDBDocumentClient,
    private readonly outbox: Outbox,
  ) {}

  async get(archiveId: string) {
    return getPublicationFacts(this.client, archiveId);
  }

  async recordPublicationDecision(
    identity: PublicationIdentity,
    messageId: string,
  ): Promise<void> {
    const facts = await this.get(identity.archiveId);

    recordPublicationDecision(facts, identity);

    try {
      await recordPublicationDecisionQuery(this.client, identity, messageId);
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

  async recordReplayPublished(
    identity: PublicationIdentity,
    messageId: string,
  ): Promise<void> {
    const facts = await this.get(identity.archiveId);

    recordReplayPublished(facts, identity);

    try {
      await recordReplayPublishedQuery(this.client, identity, messageId);
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
    messageId: string,
    outboxEntry: OutboxEntry,
  ): Promise<void> {
    const facts = await this.get(decision.archiveId);

    recordCompensationDecision(facts, decision);

    try {
      await recordCompensationDecisionTransaction(
        this.client,
        decision,
        messageId,
        outboxEntry,
      );
    } catch (error) {
      if (!isConditionalCheckFailure(error)) {
        throw error;
      }

      const current = await this.get(decision.archiveId);

      if (recordCompensationDecision(current, decision) !== current) {
        throw new PublicationConflictError(
          "publication state changed concurrently; retry the operation",
        );
      }

      const outbox = await this.outbox.get(outboxEntry.messageId);

      if (
        outbox === undefined ||
        outbox.type !== outboxEntry.type ||
        outbox.correlationId !== decision.archiveId
      ) {
        throw new PublicationConflictError(
          "compensation acknowledgement was not durably recorded",
        );
      }
    }
  }
}

export { DynamoDBPublicationLedger };
