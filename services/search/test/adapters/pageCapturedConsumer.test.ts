import { expect, it } from "vitest";
import { parsePageCaptured } from "../../src/adapters/messaging/rabbitmq/pageCapturedConsumer.js";

const event = {
  messageId: "message-1",
  correlationId: "archive-1",
  type: "PageCaptured",
  version: 1,
  occurredAt: "2026-11-22T10:00:00.000Z",
  payload: {
    archiveId: "archive-1",
    snapshotId: "snapshot-1",
    urlKey: "url-key",
    url: "https://example.com/",
    capturedAt: "2026-11-22T10:00:00.000Z",
    warcArtifacts: [
      {
        bucket: "capture-artifacts",
        key: "archive-1/snapshot-1.warc",
        sha256: "a".repeat(64),
        sizeBytes: 128,
      },
    ],
  },
};

it("parses a valid PageCaptured event envelope", () => {
  expect(parsePageCaptured(Buffer.from(JSON.stringify(event)))).toMatchObject({
    messageId: "message-1",
    correlationId: "archive-1",
    payload: {
      archiveId: "archive-1",
      snapshotId: "snapshot-1",
      warcArtifacts: [{ bucket: "capture-artifacts", sizeBytes: 128 }],
    },
  });
});

it("rejects an event whose correlation identity differs from its archive", () => {
  expect(
    parsePageCaptured(
      Buffer.from(JSON.stringify({
        ...event,
        correlationId: "another-archive",
      })),
    ),
  ).toBeNull();
});

it("rejects malformed artifact references", () => {
  expect(
    parsePageCaptured(
      Buffer.from(JSON.stringify({
        ...event,
        payload: {
          ...event.payload,
          warcArtifacts: [{ bucket: "capture-artifacts", key: "missing-checksum" }],
        },
      })),
    ),
  ).toBeNull();
});

it("rejects unsupported event versions", () => {
  expect(
    parsePageCaptured(
      Buffer.from(JSON.stringify({ ...event, version: 2 })),
    ),
  ).toBeNull();
});
