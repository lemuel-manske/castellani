import { afterAll, beforeAll, expect, it } from "vitest";
import {
  IndexingClaimLostError,
  IndexingIdentityConflictError,
} from "../../src/adapters/persistence/dynamodb/indexing-ledger.js";
import {
  SEARCH_DYNAMODB_ENDPOINT_URL,
  createDynamoDbTestSupport,
} from "../support/dynamoDb.js";

let now = 1_000_000;
const support = createDynamoDbTestSupport(() => now);

beforeAll(async () => {
  if (!SEARCH_DYNAMODB_ENDPOINT_URL?.trim()) {
    throw new Error(
      "SEARCH_DYNAMODB_ENDPOINT_URL is required; start the Search Compose dependencies and configure the integration-test environment",
    );
  }

  await support.setup();
});

afterAll(async () => {
  if (SEARCH_DYNAMODB_ENDPOINT_URL?.trim()) {
    await support.teardown();
  }
});

it("claims a snapshot and persists its attempt count", async () => {
  const result = await support.ledger.claim(
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
    support.ledger.claim("archive-2", "snapshot-2", "message-2a", 120),
    support.ledger.claim("archive-2", "snapshot-2", "message-2b", 120),
  ]);

  expect(results.filter((result) => result.status === "CLAIMED")).toHaveLength(1);
  expect(results.filter((result) => result.status === "BUSY")).toHaveLength(1);
});

it("reclaims an expired lease and increments the attempt count", async () => {
  const first = await support.ledger.claim(
    "archive-3",
    "snapshot-3",
    "message-3a",
    120,
  );
  expect(first.status).toBe("CLAIMED");

  now += 121_000;

  const second = await support.ledger.claim(
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
  await support.ledger.claim("archive-4", "snapshot-4", "message-4a", 120);

  await expect(
    support.ledger.claim("archive-other", "snapshot-4", "message-4b", 120),
  ).rejects.toBeInstanceOf(IndexingIdentityConflictError);
});

it("rejects completion by a worker whose lease was reclaimed", async () => {
  const first = await support.ledger.claim(
    "archive-5",
    "snapshot-5",
    "message-5a",
    120,
  );
  expect(first.status).toBe("CLAIMED");
  const firstClaim = first.status === "CLAIMED" ? first.claim : undefined;
  expect(firstClaim).toBeDefined();

  now += 121_000;

  const second = await support.ledger.claim(
    "archive-5",
    "snapshot-5",
    "message-5b",
    120,
  );
  expect(second.status).toBe("CLAIMED");
  const secondClaim = second.status === "CLAIMED" ? second.claim : undefined;
  expect(secondClaim).toBeDefined();

  await expect(
    support.ledger.complete(firstClaim!, "INDEXED"),
  ).rejects.toBeInstanceOf(IndexingClaimLostError);

  await support.ledger.complete(secondClaim!, "INDEXED");

  await expect(
    support.ledger.claim("archive-5", "snapshot-5", "message-5c", 120),
  ).resolves.toEqual({ status: "TERMINAL", outcome: "INDEXED" });
});
