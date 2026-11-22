import { expect, it, vi } from "vitest";
import type { Client } from "@opensearch-project/opensearch";
import { createOpenSearchDocumentWriter } from "../../src/adapters/search/opensearch.js";
import type { SearchDocument } from "../../src/domain/content.js";

const document: SearchDocument = {
  archiveId: "archive-1",
  snapshotId: "snapshot-1",
  url: "https://example.com/",
  finalUrl: "https://example.com/",
  capturedAt: "2026-11-22T10:00:00.000Z",
  contentType: "text/html",
  title: "Example",
  description: "",
  language: "en",
  text: "Example page",
};

it("uses snapshotId as the deterministic OpenSearch document ID", async () => {
  const index = vi.fn().mockResolvedValue({});
  const client = { index } as unknown as Client;
  const writer = createOpenSearchDocumentWriter(client, "archive-pages-test");

  await writer.index(document);

  expect(index).toHaveBeenCalledWith({
    index: "archive-pages-test",
    id: "snapshot-1",
    body: document,
    refresh: false,
  });
});
