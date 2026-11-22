import { expect, it } from "vitest";
import { createWarcCapturedPageReader } from "../../src/adapters/artifacts/warc.js";
import { indexCapturedPage } from "../../src/application/indexCapturedPage.js";
import type { SearchDocument } from "../../src/domain/content.js";
import type { SearchDocumentWriter } from "../../src/ports/search-index.js";
import { createCapturedPageFixture } from "../support/fixtures.js";

function collectingDocumentWriter() {
  const documents: SearchDocument[] = [];
  const writer: SearchDocumentWriter = {
    async index(document) {
      documents.push(document);
    },
  };

  return { documents, writer };
}

it("extracts and indexes a captured page using its snapshot identity", async () => {
  const fixture = createCapturedPageFixture("snapshot-1");
  const { documents, writer } = collectingDocumentWriter();

  await expect(
    indexCapturedPage(
      fixture.page,
      [fixture.artifact],
      createWarcCapturedPageReader(fixture.artifactReader),
      writer,
    ),
  ).resolves.toEqual({ outcome: "INDEXED", snapshotId: "snapshot-1" });

  expect(documents).toHaveLength(1);
  expect(documents[0]).toMatchObject({
    archiveId: "integration-archive",
    snapshotId: "snapshot-1",
    text: "Integrated content",
  });
});

it("accounts for unsupported captured content without writing a document", async () => {
  const fixture = createCapturedPageFixture("unsupported-snapshot", {
    contentType: "application/pdf",
    body: "%PDF-1.7 not searchable text",
  });
  const { documents, writer } = collectingDocumentWriter();

  await expect(
    indexCapturedPage(
      fixture.page,
      [fixture.artifact],
      createWarcCapturedPageReader(fixture.artifactReader),
      writer,
    ),
  ).resolves.toEqual({
    outcome: "UNSUPPORTED",
    snapshotId: "unsupported-snapshot",
    reasonCode: "UNSUPPORTED_CONTENT_TYPE",
  });

  expect(documents).toHaveLength(0);
});
