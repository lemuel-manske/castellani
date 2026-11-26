import { expect, it } from "vitest";

import { validateManifest, validateMessage } from "../src/contracts.js";
import {
  ARCHIVE_PUBLISHED_EVENT,
  PAGE_CAPTURED_EVENT,
} from "../src/domain/index.js";

function encode(value: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(value));
}

it("accepts a page captured message without optional fields", () => {
  const envelope = {
    type: PAGE_CAPTURED_EVENT,
    version: 1,
    messageId: "message-1",
    correlationId: "archive-1",
    occurredAt: "2026-11-20T12:00:00Z",
    payload: {
      archiveId: "archive-1",
      snapshotId: "snapshot-1",
      urlKey: "url-1",
      url: "https://example.com/",
      capturedAt: "2026-11-20T12:00:00Z",
      warcArtifacts: [
        {
          bucket: "capture-artifacts",
          key: "archive-1/snapshot-1.warc.gz",
          sha256: "a".repeat(64),
          sizeBytes: 1,
        },
      ],
    },
  };

  expect(validateMessage(encode(envelope), PAGE_CAPTURED_EVENT)).toEqual(
    envelope,
  );
});

it("rejects a contract message with an unsupported version", () => {
  const envelope = {
    type: ARCHIVE_PUBLISHED_EVENT,
    version: 2,
    messageId: "message-1",
    correlationId: "archive-1",
    occurredAt: "2026-11-20T12:00:00Z",
    payload: {
      archiveId: "archive-1",
      decisionVersion: 1,
      packageDigest: "sha256:package",
    },
  };

  expect(validateMessage(encode(envelope))).toBeNull();
});

it("accepts a contract-complete archive manifest", () => {
  expect(
    validateManifest({
      schemaVersion: 1,
      archiveId: "archive-1",
      normalizerVersion: "v1",
      seedUrl: "https://example.com/",
      createdAt: "2026-11-25T12:00:00Z",
      snapshots: [],
      failedPages: [],
    }),
  ).toBe(true);
});

it("rejects a manifest missing required contract fields", () => {
  expect(
    validateManifest({
      schemaVersion: 1,
      archiveId: "archive-1",
      createdAt: "2026-11-25T12:00:00Z",
      snapshots: [],
    }),
  ).toBe(false);
});
