import { afterEach, describe, expect, it } from "vitest";

import { createSearchServer } from "../../src/api/server.js";
import type { SearchDocumentReader } from "../../src/ports/search-reader.js";

import { createSearchDocumentFixture } from "../support/fixtures.js";
import {
  dynamodb,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";

setupIntegrationEnvironment("dynamodb");

describe("published search behavior", () => {
  let server: ReturnType<typeof createSearchServer> | undefined;

  afterEach(async () => {
    await server?.close();
    server = undefined;
  });

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

    server = createSearchServer(
      reader,
      dynamodb.publicationLedger,
      dynamodb.manifestLedger,
    );

    await dynamodb.manifestLedger.record({
      archiveId: document.archiveId,
      manifestDigest: "manifest-digest",
      collectionId: "integration-collection",
      snapshotIds: [document.snapshotId],
    });

    await dynamodb.publicationLedger.recordPublicationDecision(identity);

    const unpublished = await server.inject({
      method: "GET",
      url: "/search?q=integration&collectionId=integration-collection",
    });

    expect(unpublished.statusCode).toBe(200);
    expect(unpublished.json().results).toEqual([]);

    await dynamodb.publicationLedger.recordReplayPublished(identity);

    const published = await server.inject({
      method: "GET",
      url: "/search?q=integration&collectionId=integration-collection",
    });

    expect(published.statusCode).toBe(200);
    expect(published.json().results).toMatchObject([
      {
        archiveId: document.archiveId,
        snapshotId: document.snapshotId,
        url: document.url,
        title: document.title,
      },
    ]);
  });
});
