import { expect, it } from "vitest";
import { reconcileArchiveManifest } from "../../src/application/reconcileArchiveManifest.js";
import {
  dynamodb,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";

setupIntegrationEnvironment("dynamodb");

it("reconciles an immutable manifest against persisted archive ledger entries", async () => {
  const indexed = await dynamodb.ledger.claim(
    "manifest-archive",
    "manifest-snapshot-1",
    "manifest-message-1",
    120,
  );
  const unexpected = await dynamodb.ledger.claim(
    "manifest-archive",
    "unlisted-snapshot",
    "manifest-message-2",
    120,
  );

  await dynamodb.ledger.complete(
    (indexed as Extract<typeof indexed, { status: "CLAIMED" }>).claim,
    "INDEXED",
  );

  expect(unexpected.status).toBe("CLAIMED");

  await expect(
    reconcileArchiveManifest(
      "manifest-archive",
      [
        { snapshotId: "manifest-snapshot-1" },
        { snapshotId: "manifest-snapshot-2" },
      ],
      dynamodb.ledger,
    ),
  ).resolves.toEqual({
    expectedCount: 2,
    terminalCount: 1,
    missingSnapshotIds: ["manifest-snapshot-2"],
    unexpectedSnapshotIds: ["unlisted-snapshot"],
    complete: false,
  });
});
