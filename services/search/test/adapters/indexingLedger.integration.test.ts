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

it("lists only the snapshots belonging to the requested archive", async () => {
  await dynamodb.ledger.claim("archive-list-a", "snapshot-list-a1", "message-list-a1", 120);
  await dynamodb.ledger.claim("archive-list-a", "snapshot-list-a2", "message-list-a2", 120);
  await dynamodb.ledger.claim("archive-list-b", "snapshot-list-b1", "message-list-b1", 120);

  await expect(dynamodb.ledger.listByArchive("archive-list-a")).resolves.toEqual([
    { snapshotId: "snapshot-list-a1", outcome: "PROCESSING" },
    { snapshotId: "snapshot-list-a2", outcome: "PROCESSING" },
  ]);
});

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

it("marks a snapshot terminal when its final claim lease expires", async () => {
  const first = await dynamodb.ledger.claim(
    "archive-6",
    "snapshot-6",
    "message-6a",
    120,
    1,
  );

  expect(first).toMatchObject({
    status: "CLAIMED",
    claim: { attempts: 1 },
  });

  clock.now += 121_000;

  await expect(
    dynamodb.ledger.claim(
      "archive-6",
      "snapshot-6",
      "message-6b",
      120,
      1,
    ),
  ).resolves.toEqual({ status: "TERMINAL", outcome: "FAILED" });
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

  const firstClaim = (first as Extract<typeof first, { status: "CLAIMED" }>).claim;
  const secondClaim = (second as Extract<typeof second, { status: "CLAIMED" }>).claim;

  await expect(
    dynamodb.ledger.complete(firstClaim, "INDEXED"),
  ).rejects.toBeInstanceOf(IndexingClaimLostError);

  await dynamodb.ledger.complete(secondClaim, "INDEXED");

  await expect(
    dynamodb.ledger.claim("archive-5", "snapshot-5", "message-5c", 120),
  ).resolves.toEqual({ status: "TERMINAL", outcome: "INDEXED" });
});
