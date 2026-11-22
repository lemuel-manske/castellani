import { createHash } from "node:crypto";
import { Readable } from "node:stream";
import { gzipSync } from "node:zlib";
import { expect, it } from "vitest";
import type { IndexingOutcome } from "../../src/domain.js";
import type { SearchDocument } from "../../src/domain/content.js";
import { createWarcCapturedPageReader } from "../../src/adapters/artifacts/warc.js";
import { processPageCaptured } from "../../src/application/processPageCaptured.js";
import type { IndexingClaimResult, IndexingLedger, SnapshotClaim } from "../../src/ports/indexing-ledger.js";
import type { ArtifactObjectReader } from "../../src/ports/artifacts.js";
import type { SearchDocumentWriter } from "../../src/ports/search-index.js";

const now = 1_000_000;

class InMemoryIndexingLedger implements IndexingLedger {
  private readonly entries = new Map<string, {
    archiveId: string;
    state: IndexingOutcome;
    attempts: number;
    token?: string;
    leaseUntil?: number;
  }>();

  async claim(archiveId: string, snapshotId: string, _messageId: string, leaseDurationSeconds: number): Promise<IndexingClaimResult> {
    const entry = this.entries.get(snapshotId);
    if (entry !== undefined && entry.archiveId !== archiveId) throw new Error("snapshot identity conflict");
    if (entry?.state === "INDEXED" || entry?.state === "UNSUPPORTED" || entry?.state === "FAILED") {
      return { status: "TERMINAL", outcome: entry.state };
    }
    if (entry?.state === "PROCESSING" && (entry.leaseUntil ?? 0) > now) {
      return { status: "BUSY", leaseUntil: entry.leaseUntil ?? now };
    }
    const attempts = (entry?.attempts ?? 0) + 1;
    const token = `claim-${attempts}`;
    this.entries.set(snapshotId, { archiveId, state: "PROCESSING", attempts, token, leaseUntil: now + leaseDurationSeconds });
    return { status: "CLAIMED", claim: { archiveId, snapshotId, token, attempts } };
  }

  async complete(claim: SnapshotClaim, outcome: Extract<IndexingOutcome, "INDEXED" | "UNSUPPORTED" | "FAILED">): Promise<void> {
    const entry = this.entries.get(claim.snapshotId);
    if (entry?.token !== claim.token) throw new Error("claim ownership lost");
    entry.state = outcome;
    delete entry.token;
    delete entry.leaseUntil;
  }

  async release(claim: SnapshotClaim, _reason: string): Promise<void> {
    const entry = this.entries.get(claim.snapshotId);
    if (entry?.token !== claim.token) throw new Error("claim ownership lost");
    entry.state = "PENDING";
    delete entry.token;
    delete entry.leaseUntil;
  }
}

class InMemorySearchDocumentWriter implements SearchDocumentWriter {
  readonly documents: SearchDocument[] = [];
  async index(document: SearchDocument): Promise<void> {
    this.documents.push(document);
  }
}

function capturedEvent() {
  const response = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<html><body><h1>Indexed content</h1></body></html>";
  const warc = [
    "WARC/1.1",
    "WARC-Type: response",
    "WARC-Target-URI: https://example.com/final",
    "WARC-Date: 2026-11-22T10:00:00Z",
    "Content-Type: application/http; msgtype=response",
    `Content-Length: ${Buffer.byteLength(response)}`,
    "",
    response,
    "",
    "",
  ].join("\r\n");
  const bytes = gzipSync(Buffer.from(warc));
  return {
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
      warcArtifacts: [{
        bucket: "capture-artifacts",
        key: "archive-1/snapshot-1.warc",
        sha256: createHash("sha256").update(bytes).digest("hex"),
        sizeBytes: bytes.byteLength,
      }],
    },
    bytes,
  };
}

function dependencies(ledger: IndexingLedger, writer: InMemorySearchDocumentWriter) {
  const event = capturedEvent();
  const artifactReader: ArtifactObjectReader = {
    getObject: () => Promise.resolve(Readable.from([event.bytes])),
  };
  return {
    event,
    dependencies: {
      ledger,
      capturedPageReader: createWarcCapturedPageReader(artifactReader),
      documentWriter: writer,
    },
  };
}

it("claims, extracts, indexes, and completes a captured snapshot", async () => {
  const ledger = new InMemoryIndexingLedger();
  const writer = new InMemorySearchDocumentWriter();
  const fixture = dependencies(ledger, writer);

  await expect(processPageCaptured(fixture.event, fixture.dependencies))
    .resolves.toEqual({ status: "COMPLETED", outcome: "INDEXED" });

  expect(writer.documents).toHaveLength(1);
  expect(writer.documents[0]).toMatchObject({
    archiveId: "archive-1",
    snapshotId: "snapshot-1",
    text: "Indexed content",
  });
});

it("does not repeat indexing after a terminal result", async () => {
  const ledger = new InMemoryIndexingLedger();
  const writer = new InMemorySearchDocumentWriter();
  const fixture = dependencies(ledger, writer);
  const claim = await ledger.claim("archive-1", "snapshot-1", "first", 120);
  expect(claim.status).toBe("CLAIMED");
  const ownedClaim = claim.status === "CLAIMED" ? claim.claim : undefined;
  expect(ownedClaim).toBeDefined();
  await ledger.complete(ownedClaim!, "INDEXED");

  await expect(processPageCaptured(fixture.event, fixture.dependencies))
    .resolves.toEqual({ status: "DUPLICATE", outcome: "INDEXED" });
  expect(writer.documents).toHaveLength(0);
});

it("does not process a snapshot while another worker holds its lease", async () => {
  const ledger = new InMemoryIndexingLedger();
  const writer = new InMemorySearchDocumentWriter();
  const fixture = dependencies(ledger, writer);
  await ledger.claim("archive-1", "snapshot-1", "first", 120);

  await expect(processPageCaptured(fixture.event, fixture.dependencies))
    .resolves.toEqual({ status: "BUSY" });
  expect(writer.documents).toHaveLength(0);
});

it("marks the snapshot failed when the maximum indexing attempt is exhausted", async () => {
  const ledger = new InMemoryIndexingLedger();
  const writer = new InMemorySearchDocumentWriter();
  const fixture = dependencies(ledger, writer);
  const first = await ledger.claim("archive-1", "snapshot-1", "first", 120);
  expect(first.status).toBe("CLAIMED");
  const firstClaim = first.status === "CLAIMED" ? first.claim : undefined;
  expect(firstClaim).toBeDefined();
  await ledger.release(firstClaim!, "temporary failure");
  const second = await ledger.claim("archive-1", "snapshot-1", "second", 120);
  expect(second.status).toBe("CLAIMED");
  const secondClaim = second.status === "CLAIMED" ? second.claim : undefined;
  expect(secondClaim).toBeDefined();
  await ledger.release(secondClaim!, "temporary failure");
  const third = await ledger.claim("archive-1", "snapshot-1", "third", 120);
  expect(third.status).toBe("CLAIMED");
  const thirdClaim = third.status === "CLAIMED" ? third.claim : undefined;
  expect(thirdClaim).toBeDefined();
  await ledger.release(thirdClaim!, "temporary failure");
  const fourth = await ledger.claim("archive-1", "snapshot-1", "fourth", 120);
  expect(fourth.status).toBe("CLAIMED");
  const fourthClaim = fourth.status === "CLAIMED" ? fourth.claim : undefined;
  expect(fourthClaim).toBeDefined();
  await ledger.release(fourthClaim!, "temporary failure");

  const failingReader = { async read() { throw new Error("artifact unavailable"); } };
  await expect(processPageCaptured(fixture.event, {
    ledger,
    capturedPageReader: failingReader,
    documentWriter: writer,
    maxAttempts: 5,
  })).resolves.toEqual({ status: "COMPLETED", outcome: "FAILED" });
  expect(writer.documents).toHaveLength(0);
});
