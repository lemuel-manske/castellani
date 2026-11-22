import { expect, it, vi } from "vitest";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import {
  DynamoDBIndexingLedger,
  IndexingClaimLostError,
  IndexingIdentityConflictError,
} from "../../src/adapters/persistence/dynamodb/indexing-ledger.js";
import type { SnapshotClaim } from "../../src/ports/indexing-ledger.js";

const claim: SnapshotClaim = {
  archiveId: "archive-1",
  snapshotId: "snapshot-1",
  token: "claim-1",
  attempts: 1,
};

const conditionalFailure = () =>
  Object.assign(new Error("conditional check failed"), {
    name: "ConditionalCheckFailedException",
  });

it("acquires a snapshot claim and increments its attempt count", async () => {
  const send = vi.fn().mockResolvedValue({ Attributes: { attempts: 1 } });
  const client = { send } as unknown as DynamoDBDocumentClient;
  const ledger = new DynamoDBIndexingLedger(
    client,
    "search_indexing_ledger",
    () => 1_000_000,
  );

  await expect(
    ledger.claim("archive-1", "snapshot-1", "message-1", 120),
  ).resolves.toMatchObject({
    status: "CLAIMED",
    claim: { archiveId: "archive-1", snapshotId: "snapshot-1", attempts: 1 },
  });

  expect(send).toHaveBeenCalledOnce();
});

it("reclaims an expired processing lease and increments attempts", async () => {
  const send = vi.fn().mockResolvedValue({ Attributes: { attempts: 2 } });
  const client = { send } as unknown as DynamoDBDocumentClient;
  const ledger = new DynamoDBIndexingLedger(
    client,
    "search_indexing_ledger",
    () => 1_000_000,
  );

  await expect(
    ledger.claim("archive-1", "snapshot-1", "message-2", 120),
  ).resolves.toMatchObject({
    status: "CLAIMED",
    claim: { attempts: 2 },
  });

  const update = send.mock.calls[0]?.[0].input;
  expect(update.ConditionExpression).toContain("#lease <= :now");
  expect(update.ExpressionAttributeValues).toMatchObject({
    ":now": 1000,
    ":lease": 1120,
  });
});

it("does not allow a different archive to claim an existing snapshot", async () => {
  const send = vi
    .fn()
    .mockRejectedValueOnce(conditionalFailure())
    .mockResolvedValueOnce({
      Item: {
        archiveId: "archive-original",
        snapshotId: "snapshot-1",
        state: "PENDING",
      },
    });
  const client = { send } as unknown as DynamoDBDocumentClient;
  const ledger = new DynamoDBIndexingLedger(client, "search_indexing_ledger");

  await expect(
    ledger.claim("archive-other", "snapshot-1", "message-2", 120),
  ).rejects.toBeInstanceOf(IndexingIdentityConflictError);

  const update = send.mock.calls[0]?.[0].input;
  expect(update.ConditionExpression).toContain("#archive = :archive");
  expect(send).toHaveBeenCalledTimes(2);
});

it("returns busy while another claim has an unexpired lease", async () => {
  const send = vi
    .fn()
    .mockRejectedValueOnce(conditionalFailure())
    .mockResolvedValueOnce({
      Item: {
        archiveId: "archive-1",
        snapshotId: "snapshot-1",
        state: "PROCESSING",
        leaseUntil: 1120,
      },
    });
  const client = { send } as unknown as DynamoDBDocumentClient;
  const ledger = new DynamoDBIndexingLedger(
    client,
    "search_indexing_ledger",
    () => 1_000_000,
  );

  await expect(
    ledger.claim("archive-1", "snapshot-1", "message-2", 120),
  ).resolves.toEqual({ status: "BUSY", leaseUntil: 1120 });
});

it("returns the stored terminal outcome without reclaiming the snapshot", async () => {
  const send = vi
    .fn()
    .mockRejectedValueOnce(conditionalFailure())
    .mockResolvedValueOnce({
      Item: {
        archiveId: "archive-1",
        snapshotId: "snapshot-1",
        state: "INDEXED",
      },
    });
  const client = { send } as unknown as DynamoDBDocumentClient;
  const ledger = new DynamoDBIndexingLedger(client, "search_indexing_ledger");

  await expect(
    ledger.claim("archive-1", "snapshot-1", "message-2", 120),
  ).resolves.toEqual({ status: "TERMINAL", outcome: "INDEXED" });
});

it("rejects completion when the claim token no longer owns the snapshot", async () => {
  const send = vi.fn().mockRejectedValue(conditionalFailure());
  const client = { send } as unknown as DynamoDBDocumentClient;
  const ledger = new DynamoDBIndexingLedger(client, "search_indexing_ledger");

  await expect(ledger.complete(claim, "INDEXED")).rejects.toBeInstanceOf(
    IndexingClaimLostError,
  );
});

it("rejects release when the claim token no longer owns the snapshot", async () => {
  const send = vi.fn().mockRejectedValue(conditionalFailure());
  const client = { send } as unknown as DynamoDBDocumentClient;
  const ledger = new DynamoDBIndexingLedger(client, "search_indexing_ledger");

  await expect(ledger.release(claim, "temporary failure")).rejects.toBeInstanceOf(
    IndexingClaimLostError,
  );
});
