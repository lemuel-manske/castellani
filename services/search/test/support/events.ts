import { randomUUID } from "node:crypto";

import type { ArtifactRef, PageCaptured } from "../../src/indexing/model.js";

type PageCapturedFields = {
  archiveId?: string;
  snapshotId?: string;
  url?: string;
  finalUrl?: string;
  capturedAt?: string;
  warcArtifacts: ArtifactRef[];
};

/** A `PageCaptured` v1 envelope as published by Capture. */
export function pageCapturedMessage(fields: PageCapturedFields): Record<string, unknown> {
  const archiveId = fields.archiveId ?? `archive-${randomUUID()}`;
  const url = fields.url ?? "https://example.org/history";

  return {
    messageId: randomUUID(),
    correlationId: archiveId,
    type: "PageCaptured",
    version: 1,
    occurredAt: "2026-11-01T12:00:01Z",
    payload: {
      archiveId,
      snapshotId: fields.snapshotId ?? `snapshot-${randomUUID()}`,
      urlKey: url,
      url,
      ...(fields.finalUrl ? { finalUrl: fields.finalUrl } : {}),
      capturedAt: fields.capturedAt ?? "2026-11-01T12:00:00Z",
      warcArtifacts: fields.warcArtifacts,
    },
  };
}

/** The decoded event the indexer receives for a message. */
export function pageCaptured(fields: PageCapturedFields): PageCaptured {
  const message = pageCapturedMessage(fields);

  return { messageId: message.messageId as string, ...(message.payload as Omit<PageCaptured, "messageId">) };
}
