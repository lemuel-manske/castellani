import { ConditionalCheckFailedException, TransactionCanceledException } from "@aws-sdk/client-dynamodb";
import {
  type DynamoDBDocumentClient,
  GetCommand,
  QueryCommand,
  ScanCommand,
  TransactWriteCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";

import type {
  ArchivePage,
  ArchiveState,
  ArchiveVisibility,
  ArtifactRef,
  IndexingCounts,
  ManifestRecord,
  PublicationFact,
  VisibilityResult,
} from "../indexing/model.js";
import { outboxPut } from "../outbox/dynamodb-outbox.js";
import type { OutgoingEvent } from "../outbox/outbox.js";

/** Sparse GSI over `reconcilePending`: only archives awaiting reconciliation. */
export const RECONCILE_INDEX = "reconcile-pending-index";
const PENDING = "PENDING";

type Item = {
  archiveId: string;
  decisionVersion?: number;
  decisionDigest?: string;
  publishedVersion?: number;
  publishedDigest?: string;
  compensationVersion?: number;
  manifestDigest?: string;
  manifestRef?: ArtifactRef;
  manifestExpected?: number;
  indexingReported?: IndexingCounts;
  readyReported?: boolean;
  compensationAcknowledged?: boolean;
  reconcileRequests?: number;
};

/**
 * `search_publications`: per-archive publication facts, manifest, indexed
 * counts and reconciliation (repair) status, keyed by `archiveId`. Each fact
 * is written once; repeating the same fact is idempotent and a contradicting
 * fact is a conflict, so stale or reordered events cannot reverse a run
 * decision. Reports are written together with their outbox record in one
 * transaction; `onEnqueued` then wakes the dispatcher.
 */
export class DynamoPublications implements ArchiveVisibility {
  constructor(
    private readonly client: DynamoDBDocumentClient,
    private readonly table: string,
    private readonly outboxTable: string,
    private readonly onEnqueued: () => void = () => undefined,
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

  recordManifest(archiveId: string, manifest: ManifestRecord): Promise<VisibilityResult> {
    return this.record(
      archiveId,
      "SET manifestDigest = :digest, manifestRef = :ref, manifestExpected = :expected, " +
        "reconcilePending = :pending, updatedAt = :now ADD reconcileRequests :one",
      "attribute_not_exists(manifestDigest) OR manifestDigest = :digest",
      {
        ":digest": manifest.digest,
        ":ref": manifest.ref,
        ":expected": manifest.expected,
        ":pending": PENDING,
        ":one": 1,
      },
      (state) => `archive ${archiveId} already has immutable manifest ${state.manifest?.digest ?? "unknown"}`,
    );
  }

  async requestReconcile(archiveId: string): Promise<void> {
    await this.client.send(
      new UpdateCommand({
        TableName: this.table,
        Key: { archiveId },
        UpdateExpression: "SET reconcilePending = :pending ADD reconcileRequests :one",
        ExpressionAttributeValues: { ":pending": PENDING, ":one": 1 },
      }),
    );
  }

  async pendingReconciliations(limit: number): Promise<string[]> {
    const response = await this.client.send(
      new QueryCommand({
        TableName: this.table,
        IndexName: RECONCILE_INDEX,
        KeyConditionExpression: "reconcilePending = :pending",
        ExpressionAttributeValues: { ":pending": PENDING },
        Limit: limit,
      }),
    );

    return (response.Items ?? []).map((item) => String(item.archiveId));
  }

  /**
   * Scans for archives with a recorded manifest. `next` is the last archive ID
   * of the page, since the table's key is `archiveId` alone.
   */
  async archivesWithManifest(limit: number, after?: string): Promise<ArchivePage> {
    const response = await this.client.send(
      new ScanCommand({
        TableName: this.table,
        Limit: limit,
        ProjectionExpression: "archiveId",
        FilterExpression: "attribute_exists(manifestDigest)",
        ...(after !== undefined ? { ExclusiveStartKey: { archiveId: after } } : {}),
      }),
    );
    const last: unknown = response.LastEvaluatedKey?.archiveId;

    return {
      archiveIds: (response.Items ?? []).map((item) => String(item.archiveId)),
      ...(typeof last === "string" ? { next: last } : {}),
    };
  }

  async clearReconcile(archiveId: string, requests: number): Promise<boolean> {
    try {
      await this.client.send(
        new UpdateCommand({
          TableName: this.table,
          Key: { archiveId },
          UpdateExpression: "REMOVE reconcilePending",
          ConditionExpression: "reconcileRequests = :requests",
          ExpressionAttributeValues: { ":requests": requests },
        }),
      );

      return true;
    } catch (error) {
      if (error instanceof ConditionalCheckFailedException) {
        return false;
      }

      throw error;
    }
  }

  reportIndexing(archiveId: string, counts: IndexingCounts, event: OutgoingEvent): Promise<void> {
    return this.report(
      archiveId,
      "SET indexingReported = :counts",
      "attribute_exists(manifestDigest) AND attribute_not_exists(indexingReported)",
      { ":counts": counts },
      event,
    );
  }

  reportReady(archiveId: string, event: OutgoingEvent): Promise<void> {
    return this.report(
      archiveId,
      "SET readyReported = :true",
      "attribute_exists(indexingReported) AND attribute_not_exists(readyReported)",
      { ":true": true },
      event,
    );
  }

  acknowledgeCompensation(archiveId: string, event: OutgoingEvent): Promise<void> {
    return this.report(
      archiveId,
      "SET compensationAcknowledged = :true",
      "attribute_exists(compensationVersion) AND attribute_not_exists(compensationAcknowledged)",
      { ":true": true },
      event,
    );
  }

  /**
   * Writes the reported state and its outbox record atomically. A cancelled
   * condition means the report was already made, with its record enqueued
   * by that earlier transaction, so repeating it is a no-op.
   */
  private async report(
    archiveId: string,
    update: string,
    condition: string,
    values: Record<string, unknown>,
    event: OutgoingEvent,
  ): Promise<void> {
    const now = new Date();

    try {
      await this.client.send(
        new TransactWriteCommand({
          TransactItems: [
            {
              Update: {
                TableName: this.table,
                Key: { archiveId },
                UpdateExpression: `${update}, updatedAt = :now`,
                ConditionExpression: condition,
                ExpressionAttributeValues: { ...values, ":now": now.toISOString() },
              },
            },
            outboxPut(this.outboxTable, event, now),
          ],
        }),
      );
    } catch (error) {
      if (error instanceof TransactionCanceledException && wasConditionFailure(error)) {
        return;
      }

      throw error;
    }

    this.onEnqueued();
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
  const state: ArchiveState = { archiveId, reconcileRequests: item?.reconcileRequests ?? 0 };

  if (item?.decisionVersion !== undefined && item.decisionDigest !== undefined) {
    state.decision = { decisionVersion: item.decisionVersion, packageDigest: item.decisionDigest };
  }

  if (item?.publishedVersion !== undefined && item.publishedDigest !== undefined) {
    state.published = { decisionVersion: item.publishedVersion, packageDigest: item.publishedDigest };
  }

  if (item?.compensationVersion !== undefined) {
    state.compensationVersion = item.compensationVersion;
  }

  if (item?.manifestDigest !== undefined && item.manifestRef !== undefined && item.manifestExpected !== undefined) {
    state.manifest = { digest: item.manifestDigest, ref: item.manifestRef, expected: item.manifestExpected };
  }

  if (item?.indexingReported !== undefined) {
    state.indexingReported = item.indexingReported;
  }

  if (item?.readyReported === true) {
    state.readyReported = true;
  }

  if (item?.compensationAcknowledged === true) {
    state.compensationAcknowledged = true;
  }

  return state;
}

function wasConditionFailure(error: TransactionCanceledException): boolean {
  const reasons = error.CancellationReasons ?? [];

  return reasons.some((reason) => reason.Code === "ConditionalCheckFailed");
}

function describe(fact: PublicationFact | undefined): string {
  return fact ? `v${fact.decisionVersion} (${fact.packageDigest})` : "none";
}
