import { it, expect } from "vitest";
import { extractSearchableContent } from "../../src/domain/content.js";
import type { CapturedPage } from "../../src/domain/content.js";

const page = (overrides: Partial<CapturedPage> = {}): CapturedPage => ({
  archiveId: "archive-1",
  snapshotId: "snapshot-1",
  url: "https://example.com/",
  capturedAt: "2026-11-22T10:00:00.000Z",
  contentType: "text/html; charset=utf-8",
  content: "<html lang='en'><head><title>Example</title><meta name='description' content='A page'></head><body><nav>Menu</nav><main><h1>Hello</h1><p>World</p><script>secret()</script></main></body></html>",
  ...overrides,
});

it("extracts searchable text and page metadata from HTML", () => {
  const result = extractSearchableContent(page());

  expect(result.kind).toBe("INDEXABLE");
  if (result.kind !== "INDEXABLE") return;

  expect(result.document).toMatchObject({
    archiveId: "archive-1",
    snapshotId: "snapshot-1",
    url: "https://example.com/",
    finalUrl: "https://example.com/",
    contentType: "text/html",
    title: "Example",
    description: "A page",
    language: "en",
    text: "Hello World",
  });
});

it("uses the final URL when supplied", () => {
  const result = extractSearchableContent(page({ finalUrl: "https://example.com/final" }));

  expect(result.kind).toBe("INDEXABLE");
  if (result.kind !== "INDEXABLE") return;

  expect(result.document.finalUrl).toBe("https://example.com/final");
});

it("extracts plain text without HTML parsing", () => {
  const result = extractSearchableContent(
    page({ contentType: "text/plain", content: "  Hello\n\tworld  " }),
  );

  expect(result.kind).toBe("INDEXABLE");
  if (result.kind !== "INDEXABLE") return;

  expect(result.document.text).toBe("Hello world");
  expect(result.document.title).toBe("");
});

it("returns an unsupported outcome for non-text content", () => {
  expect(
    extractSearchableContent(page({ contentType: "application/pdf", content: "binary" })),
  ).toEqual({ kind: "UNSUPPORTED", reasonCode: "UNSUPPORTED_CONTENT_TYPE" });
});

it("returns an unsupported outcome when extracted text is empty", () => {
  expect(
    extractSearchableContent(page({ content: "<html><body><nav>Only navigation</nav></body></html>" })),
  ).toEqual({ kind: "UNSUPPORTED", reasonCode: "EMPTY_CONTENT" });
});

it("limits extracted text to the configured maximum", () => {
  const result = extractSearchableContent(
    page({ contentType: "text/plain", content: "abcdefghij" }),
    { maxTextLength: 4 },
  );

  expect(result.kind).toBe("INDEXABLE");
  if (result.kind !== "INDEXABLE") return;

  expect(result.document.text).toBe("abcd");
});
