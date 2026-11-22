import { expect, it } from "vitest";
import {
  clock,
  dynamodb,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import {
  IndexingClaimLostError,
  IndexingIdentityConflictError,
} from "../../src/adapters/persistence/dynamodb/indexing-ledger.js";

setupIntegrationEnvironment("dynamodb");

it("claims a snapshot and persists its attempt count", async () => {
  const result = await dynamodb.ledger.claim(
    "archive-1",
    "snapshot-1",
    "message-1",
    120,
  );

  expect(result).toMatchObject({
    status: "CLAIMED",
    claim: { archiveId: "archive-1", snapshotId: "snapshot-1", attempts: 1 },
  });
});

it("allows only one concurrent claim for the same snapshot", async () => {
  const results = await Promise.all([
    dynamodb.ledger.claim("archive-2", "snapshot-2", "message-2a", 120),
    dynamodb.ledger.claim("archive-2", "snapshot-2", "message-2b", 120),
  ]);

  expect(results.filter((result) => result.status === "CLAIMED")).toHaveLength(
    1,
  );
  expect(results.filter((result) => result.status === "BUSY")).toHaveLength(1);
});

it("reclaims an expired lease and increments the attempt count", async () => {
  const first = await dynamodb.ledger.claim(
    "archive-3",
    "snapshot-3",
    "message-3a",
    120,
  );
  expect(first.status).toBe("CLAIMED");

  clock.now += 121_000;

  const second = await dynamodb.ledger.claim(
    "archive-3",
    "snapshot-3",
    "message-3b",
    120,
  );

  expect(second).toMatchObject({
    status: "CLAIMED",
    claim: { attempts: 2 },
  });
});

it("rejects a claim when a snapshot belongs to another archive", async () => {
  await dynamodb.ledger.claim("archive-4", "snapshot-4", "message-4a", 120);

  await expect(
    dynamodb.ledger.claim("archive-other", "snapshot-4", "message-4b", 120),
  ).rejects.toBeInstanceOf(IndexingIdentityConflictError);
});

it("rejects completion by a worker whose lease was reclaimed", async () => {
  const first = await dynamodb.ledger.claim(
    "archive-5",
    "snapshot-5",
    "message-5a",
    120,
  );
  expect(first.status).toBe("CLAIMED");

  clock.now += 121_000;

  const second = await dynamodb.ledger.claim(
    "archive-5",
    "snapshot-5",
    "message-5b",
    120,
  );
  expect(second.status).toBe("CLAIMED");

  if (first.status !== "CLAIMED" || second.status !== "CLAIMED") {
    throw new Error("Expected both lease claims to succeed");
  }

  await expect(
    dynamodb.ledger.complete(first.claim, "INDEXED"),
  ).rejects.toBeInstanceOf(IndexingClaimLostError);

  await dynamodb.ledger.complete(second.claim, "INDEXED");

  await expect(
    dynamodb.ledger.claim("archive-5", "snapshot-5", "message-5c", 120),
  ).resolves.toEqual({ status: "TERMINAL", outcome: "INDEXED" });
});
