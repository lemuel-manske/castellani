import { expect, it } from "vitest";

import { parsePageCaptured } from "../../../../src/adapters/messaging/rabbitmq/pageCapturedConsumer.js";
import { PAGE_CAPTURED_EVENT } from "../../../../src/domain.js";

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

function encode(value: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(value));
}

it("accepts a contract-valid envelope without optional tracking fields", () => {
  expect(parsePageCaptured(encode(envelope))).toEqual(envelope);
});

it("rejects an envelope that violates the contract", () => {
  const malformed = {
    ...envelope,
    payload: {
      ...envelope.payload,
      warcArtifacts: [
        {
          ...envelope.payload.warcArtifacts[0],
          sha256: "not-a-sha256-digest",
        },
      ],
    },
  };

  expect(parsePageCaptured(encode(malformed))).toBeNull();
});

it("rejects an envelope whose archiveId differs from the correlationId", () => {
  const mismatched = {
    ...envelope,
    payload: { ...envelope.payload, archiveId: "archive-2" },
  };

  expect(parsePageCaptured(encode(mismatched))).toBeNull();
});
