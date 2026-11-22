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
    finalUrl: "https://example.com/final",
    redirectChain: ["https://example.com/", "https://example.com/final"],
    capturedAt: "2026-11-22T10:00:00.000Z",
    contentType: "text/html",
    warcArtifacts: [
      {
        bucket: "capture-artifacts",
        key: "capture-staging/archive-1/url-key/attempt-1/snapshot-1/page.warc.gz",
        sha256: "a".repeat(64),
        sizeBytes: 128,
        versionId: "version-1",
      },
    ],
  },
};

it("parses the PageCaptured envelope emitted by Capture", () => {
  expect(parsePageCaptured(Buffer.from(JSON.stringify(event)))).toEqual({
    messageId: "message-1",
    correlationId: "archive-1",
    occurredAt: "2026-11-22T10:00:00.000Z",
    payload: {
      archiveId: "archive-1",
      snapshotId: "snapshot-1",
      urlKey: "url-key",
      url: "https://example.com/",
      finalUrl: "https://example.com/final",
      redirectChain: ["https://example.com/", "https://example.com/final"],
      capturedAt: "2026-11-22T10:00:00.000Z",
      contentType: "text/html",
      warcArtifacts: [
        {
          bucket: "capture-artifacts",
          key: "capture-staging/archive-1/url-key/attempt-1/snapshot-1/page.warc.gz",
          sha256: "a".repeat(64),
          sizeBytes: 128,
          versionId: "version-1",
        },
      ],
    },
  });
});

it("rejects an event whose correlation identity differs from its archive", () => {
  expect(
    parsePageCaptured(
      Buffer.from(JSON.stringify({ ...event, correlationId: "another-archive" })),
    ),
  ).toBeNull();
});

it("rejects malformed artifact references", () => {
  expect(
    parsePageCaptured(
      Buffer.from(
        JSON.stringify({
          ...event,
          payload: {
            ...event.payload,
            warcArtifacts: [{ bucket: "capture-artifacts", key: "missing-checksum" }],
          },
        }),
      ),
    ),
  ).toBeNull();
});

it("rejects unsupported event versions", () => {
  expect(
    parsePageCaptured(Buffer.from(JSON.stringify({ ...event, version: 2 }))),
  ).toBeNull();
});

it("rejects missing producer-required capture metadata", () => {
  const payload = { ...event.payload };
  delete (payload as Partial<typeof event.payload>).finalUrl;

  expect(
    parsePageCaptured(Buffer.from(JSON.stringify({ ...event, payload }))),
  ).toBeNull();
});

it("rejects non-canonical uppercase artifact checksums", () => {
  expect(
    parsePageCaptured(
      Buffer.from(
        JSON.stringify({
          ...event,
          payload: {
            ...event.payload,
            warcArtifacts: [
              { ...event.payload.warcArtifacts[0], sha256: "A".repeat(64) },
            ],
          },
        }),
      ),
    ),
  ).toBeNull();
});