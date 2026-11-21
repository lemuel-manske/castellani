import { describe, expect, test } from "vitest";

import { Indexer, RetryableError } from "../src/indexing/indexer.js";
import { MemoryArtifacts, MemoryLedger, MemoryVisibility, RecordingIndex } from "./support/doubles.js";
import { pageCaptured } from "./support/events.js";
import { artifactRefFor, buildWarc } from "./support/warc.js";

const ARTICLE = `<!doctype html>
<html>
  <head><title>Harbour history</title><style>.x { color: red }</style></head>
  <body>
    <h1>The old harbour</h1><p>Fishing boats &amp; ferries</p><p>left at dawn.</p>
    <script>trackVisitor()</script>
  </body>
</html>`;

function fixture() {
  const ledger = new MemoryLedger();
  const artifacts = new MemoryArtifacts();
  const index = new RecordingIndex();
  const visibility = new MemoryVisibility();
  const indexer = new Indexer(ledger, artifacts, index, visibility, { maxDocumentAttempts: 2 });

  return { ledger, artifacts, index, indexer };
}

async function storeWarc(artifacts: MemoryArtifacts, key: string, url: string, body: string) {
  const warc = await buildWarc([{ url, body }]);
  artifacts.put(key, warc);

  return artifactRefFor(warc, key);
}

describe("indexing captured pages", () => {
  test("a captured HTML page becomes a snapshot document", async () => {
    const { artifacts, index, indexer, ledger } = fixture();
    const ref = await storeWarc(artifacts, "a.warc.gz", "https://example.org/history", ARTICLE);
    const event = pageCaptured({ url: "https://example.org/history", warcArtifacts: [ref] });

    const result = await indexer.handle(event);

    expect(result).toBe("indexed");
    const document = index.document(event.snapshotId);
    expect(document?.archiveId).toBe(event.archiveId);
    expect(document?.title).toBe("Harbour history");
    expect(document?.content).toBe("The old harbour Fishing boats & ferries left at dawn.");
    expect(document?.capturedAt).toBe(event.capturedAt);
    expect(ledger.statusOf(event)).toBe("INDEXED");
  });

  test("script and style content is not indexed", async () => {
    const { artifacts, index, indexer } = fixture();
    const ref = await storeWarc(artifacts, "a.warc.gz", "https://example.org/history", ARTICLE);
    const event = pageCaptured({ url: "https://example.org/history", warcArtifacts: [ref] });

    await indexer.handle(event);

    const content = index.document(event.snapshotId)?.content ?? "";
    expect(content).not.toContain("trackVisitor");
    expect(content).not.toContain("color: red");
  });

  test("a redirected page is indexed from the response of its final URL", async () => {
    const { artifacts, index, indexer } = fixture();
    const warc = await buildWarc([
      { url: "https://example.org/old", body: "<p>Moved</p>", status: 301 },
      { url: "https://example.org/new", body: "<title>New home</title><p>Current page</p>" },
    ]);
    artifacts.put("r.warc.gz", warc);
    const event = pageCaptured({
      url: "https://example.org/old",
      finalUrl: "https://example.org/new",
      warcArtifacts: [artifactRefFor(warc, "r.warc.gz")],
    });

    await indexer.handle(event);

    expect(index.document(event.snapshotId)?.title).toBe("New home");
  });

  test("redelivering an indexed snapshot does not index it again", async () => {
    const { artifacts, index, indexer } = fixture();
    const ref = await storeWarc(artifacts, "a.warc.gz", "https://example.org/history", ARTICLE);
    const event = pageCaptured({ url: "https://example.org/history", warcArtifacts: [ref] });
    await indexer.handle(event);

    const result = await indexer.handle({ ...event, messageId: "a-different-emission" });

    expect(result).toBe("duplicate");
    expect(index.writes).toBe(1);
  });
});

describe("indexing failures", () => {
  test("a page without an HTML response is recorded as not indexable", async () => {
    const { artifacts, index, indexer, ledger } = fixture();
    const warc = await buildWarc([
      { url: "https://example.org/data.json", body: "{}", contentType: "application/json" },
    ]);
    artifacts.put("j.warc.gz", warc);
    const event = pageCaptured({
      url: "https://example.org/data.json",
      warcArtifacts: [artifactRefFor(warc, "j.warc.gz")],
    });

    const result = await indexer.handle(event);

    expect(result).toBe("unsupported");
    expect(ledger.statusOf(event)).toBe("UNSUPPORTED");
    expect(index.documents.size).toBe(0);
  });

  test("an artifact failing digest verification is retried, then recorded as a terminal failure", async () => {
    const { artifacts, index, indexer, ledger } = fixture();
    const ref = await storeWarc(artifacts, "a.warc.gz", "https://example.org/history", ARTICLE);
    const event = pageCaptured({
      url: "https://example.org/history",
      warcArtifacts: [{ ...ref, sha256: "0".repeat(64) }],
    });

    await expect(indexer.handle(event)).rejects.toBeInstanceOf(RetryableError);
    expect(ledger.statusOf(event)).toBe("PENDING");

    const result = await indexer.handle(event);

    expect(result).toBe("failed");
    expect(ledger.statusOf(event)).toBe("FAILED");
    expect(index.documents.size).toBe(0);
  });

  test("an unavailable search index keeps the snapshot recoverable and indexes it once it returns", async () => {
    const { artifacts, index, indexer, ledger } = fixture();
    const ref = await storeWarc(artifacts, "a.warc.gz", "https://example.org/history", ARTICLE);
    const event = pageCaptured({ url: "https://example.org/history", warcArtifacts: [ref] });
    index.offline = true;

    await expect(indexer.handle(event)).rejects.toBeInstanceOf(RetryableError);
    await expect(indexer.handle(event)).rejects.toBeInstanceOf(RetryableError);
    await expect(indexer.handle(event)).rejects.toBeInstanceOf(RetryableError);
    expect(ledger.statusOf(event)).toBe("PENDING");

    index.offline = false;
    const result = await indexer.handle(event);

    expect(result).toBe("indexed");
    expect(ledger.statusOf(event)).toBe("INDEXED");
  });

  test("a snapshot being indexed by another worker is redelivered later", async () => {
    const { artifacts, index, indexer, ledger } = fixture();
    const ref = await storeWarc(artifacts, "a.warc.gz", "https://example.org/history", ARTICLE);
    const event = pageCaptured({ url: "https://example.org/history", warcArtifacts: [ref] });
    ledger.holdByAnotherWorker(event);

    await expect(indexer.handle(event)).rejects.toBeInstanceOf(RetryableError);

    expect(index.writes).toBe(0);
  });

  test("the same snapshot ID in another archive is a separate snapshot and never overwrites the first", async () => {
    const { artifacts, index, indexer, ledger } = fixture();
    const ref = await storeWarc(artifacts, "a.warc.gz", "https://example.org/history", ARTICLE);
    const event = pageCaptured({ url: "https://example.org/history", warcArtifacts: [ref] });
    const other = { ...event, archiveId: "another-archive" };

    await indexer.handle(event);
    await indexer.handle(other);

    expect(ledger.statusOf(event)).toBe("INDEXED");
    expect(ledger.statusOf(other)).toBe("INDEXED");
    expect([...index.documents.values()].map((d) => d.archiveId).sort()).toEqual(
      [event.archiveId, "another-archive"].sort(),
    );
  });
});
