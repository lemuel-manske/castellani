import { expect, it } from "vitest";
import { dynamodb, setupIntegrationEnvironment } from "../support/integrationEnvironment.js";

setupIntegrationEnvironment("dynamodb");

it("exposes only snapshots in a completed immutable manifest", async () => {
  await dynamodb.manifestLedger.record({
    archiveId: "manifest-membership-archive",
    manifestDigest: "a".repeat(64),
    collectionId: "collection-a",
    snapshotIds: ["manifest-snapshot-a", "manifest-snapshot-b"],
  });

  await expect(dynamodb.manifestLedger.contains(
    "manifest-membership-archive", "manifest-snapshot-a",
  )).resolves.toBe(true);
  await expect(dynamodb.manifestLedger.contains(
    "manifest-membership-archive", "not-in-manifest",
  )).resolves.toBe(false);
  await expect(dynamodb.manifestLedger.contains(
    "manifest-membership-archive", "manifest-snapshot-a", "collection-b",
  )).resolves.toBe(false);
});

it("rejects a different immutable manifest for an existing archive", async () => {
  const manifest = {
    archiveId: "immutable-manifest-archive",
    manifestDigest: "b".repeat(64),
    collectionId: "collection-b",
    snapshotIds: ["immutable-snapshot"],
  };
  await dynamodb.manifestLedger.record(manifest);

  await expect(dynamodb.manifestLedger.record({
    ...manifest,
    manifestDigest: "c".repeat(64),
  })).rejects.toThrow("archive manifest conflicts");
});
