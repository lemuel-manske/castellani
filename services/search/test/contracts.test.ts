import { expect, it } from "vitest";

import { validateMessage } from "../src/contracts.js";

function encode(value: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(value));
}

it("accepts a page captured message without optional fields", () => {
  const envelope = {
    type: "PageCaptured",
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

  expect(validateMessage(encode(envelope), "PageCaptured")).toEqual(envelope);
});

it("rejects a contract message with an unsupported version", () => {
  const envelope = {
    type: "ArchivePublished",
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
