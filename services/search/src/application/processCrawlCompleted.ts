import { createHash } from "node:crypto";
import type {
  ArtifactObjectReader,
  ArtifactReference,
  CapturedPageReader,
} from "../ports/artifacts.js";

import {
  CRAWL_COMPLETED_EVENT,
  PAGE_CAPTURED_EVENT,
  type CompletionCrawl,
} from "../domain.js";

import type { IndexingLedger } from "../ports/indexing-ledger.js";
import type { ManifestLedger } from "../ports/manifest-ledger.js";
import type { PublicationLedger } from "../ports/publication-ledger.js";
import type { SearchDocumentWriter } from "../ports/search-index.js";

import { validateManifest } from "../contracts.js";

import { processPageCaptured } from "./processPageCaptured.js";

import { ManifestDocument, Event } from "./types.js";

async function readArtifact(
  reader: ArtifactObjectReader,
  reference: ArtifactReference,
): Promise<Buffer> {
  const chunks: Buffer[] = [];

  for await (const chunk of await reader.getObject(reference)) {
    chunks.push(Buffer.from(chunk));
  }

  const data = Buffer.concat(chunks);

  if (data.byteLength !== reference.sizeBytes) {
    throw new Error(
      "archive manifest size does not match its immutable reference",
    );
  }

  return data;
}

function isManifestDocument(value: unknown): value is ManifestDocument {
  return validateManifest(value);
}

function parseManifest(data: Buffer, event: CompletionCrawl): ManifestDocument {
  const digest = createHash("sha256").update(data).digest("hex");

  const expectedDigest = event.manifestDigest.replace(/^sha256:/, "");

  if (digest !== expectedDigest || digest !== event.manifest.sha256) {
    throw new Error(
      "archive manifest digest does not match its immutable reference",
    );
  }

  const manifest: unknown = JSON.parse(data.toString("utf8"));

  if (!isManifestDocument(manifest)) {
    throw new Error("archive manifest does not match the v1 manifest contract");
  }

  if (manifest.archiveId !== event.archiveId) {
    throw new Error("archive manifest archive ID does not match its event");
  }

  return manifest;
}

async function processCrawlCompleted(
  event: Event<typeof CRAWL_COMPLETED_EVENT, CompletionCrawl>,
  reader: ArtifactObjectReader,
  manifestLedger: ManifestLedger,
  indexingLedger: IndexingLedger,
  capturedPageReader: CapturedPageReader,
  documentWriter: SearchDocumentWriter,
  leaseDurationSeconds: number,
  maxAttempts: number,
  publicationLedger: PublicationLedger,
): Promise<void> {
  const payload = event.payload;

  const data = await readArtifact(reader, payload.manifest);

  const manifest = parseManifest(data, payload);

  await manifestLedger.record(
    {
      archiveId: manifest.archiveId,
      manifestDigest: payload.manifestDigest,
      collectionId: manifest.collectionId ?? "",
      snapshotIds: manifest.snapshots.map(({ snapshotId }) => snapshotId),
    },
    event.messageId,
  );

  for (const snapshot of manifest.snapshots) {
    await processPageCaptured(
      {
        type: PAGE_CAPTURED_EVENT,
        version: 1,
        messageId: `manifest:${payload.manifestDigest}:${snapshot.snapshotId}`,
        correlationId: manifest.archiveId,
        occurredAt: manifest.createdAt,
        payload: {
          archiveId: manifest.archiveId,
          snapshotId: snapshot.snapshotId,
          urlKey: snapshot.urlKey,
          url: snapshot.url,
          finalUrl: snapshot.finalUrl,
          redirectChain: snapshot.redirectChain ?? [
            snapshot.url,
            snapshot.finalUrl,
          ],
          capturedAt: snapshot.capturedAt,
          warcArtifacts: snapshot.warcArtifacts,
        },
      },
      indexingLedger,
      capturedPageReader,
      documentWriter,
      leaseDurationSeconds,
      maxAttempts,
      publicationLedger,
    );
  }
}

export { processCrawlCompleted };
