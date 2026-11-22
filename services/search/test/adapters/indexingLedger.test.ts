import { expect, it, vi } from "vitest";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import {
  DynamoDBIndexingLedger,
  IndexingClaimLostError,
} from "../../src/adapters/persistence/dynamodb/indexing-ledger.js";
import type { SnapshotClaim } from "../../src/ports/indexing-ledger.js";

const claim: SnapshotClaim = {
  archiveId: "archive-1",
  snapshotId: "snapshot-1",
  token: "claim-1",
  attempts: 1,
};

it("acquires a snapshot claim and increments its attempt count", async () => {
  const send = vi.fn().mockResolvedValue({ Attributes: { attempts: 1 } });
  const client = { send } as unknown as DynamoDBDocumentClient;
  const ledger = new DynamoDBIndexingLedger(client, "search_indexing_ledger", () => 1_000_000);

  await expect(
    ledger.claim("archive-1", "snapshot-1", "message-1", 120),
  ).resolves.toMatchObject({
    status: "CLAIMED",
    claim: { archiveId: "archive-1", snapshotId: "snapshot-1", attempts: 1 },
  });

  expect(send).toHaveBeenCalledOnce();
});

it("rejects completion when the claim token no longer owns the snapshot", async () => {
  const send = vi.fn().mockRejectedValue(
    Object.assign(new Error("conditional check failed"), {
      name: "ConditionalCheckFailedException",
    }),
  );
  const client = { send } as unknown as DynamoDBDocumentClient;
  const ledger = new DynamoDBIndexingLedger(client, "search_indexing_ledger");

  await expect(ledger.complete(claim, "INDEXED")).rejects.toBeInstanceOf(
    IndexingClaimLostError,
  );
});
