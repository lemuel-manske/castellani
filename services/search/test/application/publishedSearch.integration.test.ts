import { describe, expect, it } from "vitest";

import { searchPublishedDocuments } from "../../src/application/searchPublishedDocuments.js";
import type { SearchDocumentReader } from "../../src/ports/search-reader.js";

import { createSearchDocumentFixture } from "../support/fixtures.js";
import {
  dynamodb,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";

setupIntegrationEnvironment("dynamodb");

describe("published search behavior", () => {
  it("does not expose an indexed snapshot until publication is acknowledged", async () => {
    const document = createSearchDocumentFixture();
    const identity = {
      archiveId: document.archiveId,
      decisionVersion: 1,
      packageDigest: "package-digest",
    };

    const reader: SearchDocumentReader = {
      search: async () => ({
        candidates: [
          {
            document,
            score: 1,
            snippet: "Search integration test content",
            cursor: "cursor",
          },
        ],
        nextCursor: null,
      }),
    };

    await dynamodb.manifestLedger.record({
      archiveId: document.archiveId,
      manifestDigest: "manifest-digest",
      collectionId: "integration-collection",
      snapshotIds: [document.snapshotId],
    });

    await dynamodb.publicationLedger.recordPublicationDecision(identity);

    const unpublished = await searchPublishedDocuments(
      { text: "integration", collectionId: "integration-collection" },
      reader,
      dynamodb.publicationLedger,
      dynamodb.manifestLedger,
    );

    expect(unpublished.results).toEqual([]);
    expect(unpublished.nextCursor).toBeNull();

    await dynamodb.publicationLedger.recordReplayPublished(identity);

    const published = await searchPublishedDocuments(
      { text: "integration", collectionId: "integration-collection" },
      reader,
      dynamodb.publicationLedger,
      dynamodb.manifestLedger,
    );

    expect(published.results).toMatchObject([
      {
        archiveId: document.archiveId,
        snapshotId: document.snapshotId,
        url: document.url,
        capturedAt: document.capturedAt,
        title: document.title,
        snippet: "Search integration test content",
        score: 1,
      },
    ]);
    expect(published.nextCursor).toBeNull();
  });
});
