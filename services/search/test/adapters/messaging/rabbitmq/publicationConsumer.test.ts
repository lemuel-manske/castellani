import { expect, it } from "vitest";

import { parsePublicationEvent } from "../../../../src/adapters/messaging/rabbitmq/publicationConsumer.js";

const manifest = {
  bucket: "archive-manifests",
  key: "archive-1/manifest.json",
  sha256: "a".repeat(64),
  sizeBytes: 2,
};

function encode(value: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(value));
}

it("preserves the validated envelope when parsing publication events", () => {
  const envelope = {
    type: "ArchivePublicationDecided",
    version: 1,
    messageId: "message-1",
    correlationId: "archive-1",
    occurredAt: "2026-11-23T12:00:00Z",
    payload: {
      archiveId: "archive-1",
      decisionVersion: 1,
      packageDigest: "sha256:package",
    },
  };

  expect(parsePublicationEvent(encode(envelope))).toEqual(envelope);
});

it("preserves the validated envelope when parsing completion events", () => {
  const envelope = {
    type: "CrawlCompleted",
    version: 1,
    messageId: "message-1",
    correlationId: "archive-1",
    occurredAt: "2026-11-23T12:00:00Z",
    payload: {
      archiveId: "archive-1",
      manifestDigest: `sha256:${"a".repeat(64)}`,
      manifest,
    },
  };

  expect(parsePublicationEvent(encode(envelope))).toEqual(envelope);
});

it("rejects a completion payload under a different event type", () => {
  const envelope = {
    type: "ArchivePublished",
    version: 1,
    messageId: "message-1",
    correlationId: "archive-1",
    occurredAt: "2026-11-23T12:00:00Z",
    payload: {
      archiveId: "archive-1",
      manifestDigest: `sha256:${"a".repeat(64)}`,
      manifest,
    },
  };

  expect(parsePublicationEvent(encode(envelope))).toBeNull();
});
