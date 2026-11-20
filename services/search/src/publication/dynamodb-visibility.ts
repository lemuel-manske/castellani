import { ConditionalCheckFailedException } from "@aws-sdk/client-dynamodb";
import { type DynamoDBDocumentClient, GetCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";

import type { ArchiveState, ArchiveVisibility, PublicationFact, VisibilityResult } from "../indexing/model.js";

type Item = {
  archiveId: string;
  decisionVersion?: number;
  decisionDigest?: string;
  publishedVersion?: number;
  publishedDigest?: string;
  compensationVersion?: number;
};

/**
 * Per-archive publication facts, keyed by `archiveId`. Each fact is written
 * once; repeating the same fact is idempotent and a contradicting fact is a
 * conflict, so stale or reordered events cannot reverse a run decision.
 */
export class DynamoVisibility implements ArchiveVisibility {
  constructor(
    private readonly client: DynamoDBDocumentClient,
    private readonly table: string,
  ) {}

  async get(archiveId: string): Promise<ArchiveState> {
    const { Item: item } = await this.client.send(
      new GetCommand({ TableName: this.table, Key: { archiveId }, ConsistentRead: true }),
    );

    return toState(archiveId, item as Item | undefined);
  }

  recordDecision(archiveId: string, fact: PublicationFact): Promise<VisibilityResult> {
    return this.record(
      archiveId,
      "SET decisionVersion = :version, decisionDigest = :digest, updatedAt = :now",
      "attribute_not_exists(compensationVersion) AND (attribute_not_exists(decisionVersion) OR " +
        "(decisionVersion = :version AND decisionDigest = :digest))",
      { ":version": fact.decisionVersion, ":digest": fact.packageDigest },
      (state) =>
        state.compensationVersion !== undefined
          ? `archive ${archiveId} was compensated; a publication decision cannot follow`
          : `archive ${archiveId} already has publication decision ${describe(state.decision)}`,
    );
  }

  recordPublished(archiveId: string, fact: PublicationFact): Promise<VisibilityResult> {
    return this.record(
      archiveId,
      "SET publishedVersion = :version, publishedDigest = :digest, updatedAt = :now",
      "attribute_not_exists(compensationVersion) AND (attribute_not_exists(publishedVersion) OR " +
        "(publishedVersion = :version AND publishedDigest = :digest))",
      { ":version": fact.decisionVersion, ":digest": fact.packageDigest },
      (state) =>
        state.compensationVersion !== undefined
          ? `archive ${archiveId} was compensated; it cannot be published`
          : `archive ${archiveId} was already published as ${describe(state.published)}`,
    );
  }

  recordCompensation(archiveId: string, decisionVersion: number): Promise<VisibilityResult> {
    return this.record(
      archiveId,
      "SET compensationVersion = :version, updatedAt = :now",
      "attribute_not_exists(decisionVersion) AND attribute_not_exists(publishedVersion) AND " +
        "(attribute_not_exists(compensationVersion) OR compensationVersion = :version)",
      { ":version": decisionVersion },
      (state) =>
        state.compensationVersion !== undefined
          ? `archive ${archiveId} was already compensated by decision ${state.compensationVersion}`
          : `archive ${archiveId} has an irreversible publication decision; it cannot be compensated`,
    );
  }

  private async record(
    archiveId: string,
    update: string,
    condition: string,
    values: Record<string, unknown>,
    explain: (state: ArchiveState) => string,
  ): Promise<VisibilityResult> {
    try {
      const result = await this.client.send(
        new UpdateCommand({
          TableName: this.table,
          Key: { archiveId },
          UpdateExpression: update,
          ConditionExpression: condition,
          ExpressionAttributeValues: { ...values, ":now": new Date().toISOString() },
          ReturnValues: "ALL_NEW",
        }),
      );

      return { kind: "recorded", state: toState(archiveId, result.Attributes as Item | undefined) };
    } catch (error) {
      if (!(error instanceof ConditionalCheckFailedException)) {
        throw error;
      }
    }

    return { kind: "conflict", reason: explain(await this.get(archiveId)) };
  }
}

function toState(archiveId: string, item: Item | undefined): ArchiveState {
  const state: ArchiveState = { archiveId };

  if (item?.decisionVersion !== undefined && item.decisionDigest !== undefined) {
    state.decision = { decisionVersion: item.decisionVersion, packageDigest: item.decisionDigest };
  }

  if (item?.publishedVersion !== undefined && item.publishedDigest !== undefined) {
    state.published = { decisionVersion: item.publishedVersion, packageDigest: item.publishedDigest };
  }

  if (item?.compensationVersion !== undefined) {
    state.compensationVersion = item.compensationVersion;
  }

  return state;
}

function describe(fact: PublicationFact | undefined): string {
  return fact ? `v${fact.decisionVersion} (${fact.packageDigest})` : "none";
}
