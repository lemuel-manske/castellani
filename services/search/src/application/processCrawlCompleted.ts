import { createHash } from "node:crypto";
import type {
  ArtifactObjectReader,
  ArtifactReference,
} from "../ports/artifacts.js";
import type { ManifestLedger } from "../ports/manifest-ledger.js";
import type { ProcessPageCapturedDependencies } from "./processPageCaptured.js";
import { processPageCaptured } from "./processPageCaptured.js";

interface CrawlCompletedEvent {
  archiveId: string;
  manifestDigest: string;
  manifest: ArtifactReference;
}

interface ManifestSnapshot {
  snapshotId: string;
  urlKey: string;
  url: string;
  finalUrl: string;
  redirectChain?: string[];
  capturedAt: string;
  contentType?: string;
  warcArtifacts: ArtifactReference[];
}

interface ManifestDocument {
  schemaVersion: 1;
  archiveId: string;
  collectionId?: string;
  createdAt: string;
  snapshots: ManifestSnapshot[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isArtifactReference(value: unknown): value is ArtifactReference {
  return (
    isRecord(value) &&
    isNonEmptyString(value.bucket) &&
    isNonEmptyString(value.key) &&
    isNonEmptyString(value.sha256) &&
    /^[a-f0-9]{64}$/.test(value.sha256) &&
    typeof value.sizeBytes === "number" &&
    Number.isSafeInteger(value.sizeBytes) &&
    value.sizeBytes >= 0 &&
    (value.versionId === undefined || isNonEmptyString(value.versionId))
  );
}

function isManifestSnapshot(value: unknown): value is ManifestSnapshot {
  return (
    isRecord(value) &&
    isNonEmptyString(value.snapshotId) &&
    isNonEmptyString(value.urlKey) &&
    isNonEmptyString(value.url) &&
    isNonEmptyString(value.finalUrl) &&
    isNonEmptyString(value.capturedAt) &&
    Number.isFinite(Date.parse(value.capturedAt)) &&
    (value.redirectChain === undefined ||
      (Array.isArray(value.redirectChain) &&
        value.redirectChain.every(isNonEmptyString))) &&
    (value.contentType === undefined ||
      typeof value.contentType === "string") &&
    Array.isArray(value.warcArtifacts) &&
    value.warcArtifacts.length > 0 &&
    value.warcArtifacts.every(isArtifactReference)
  );
}

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

function parseManifest(
  data: Buffer,
  event: CrawlCompletedEvent,
): ManifestDocument {
  const digest = createHash("sha256").update(data).digest("hex");
  const expectedDigest = event.manifestDigest.replace(/^sha256:/, "");

  if (digest !== expectedDigest || digest !== event.manifest.sha256) {
    throw new Error(
      "archive manifest digest does not match its immutable reference",
    );
  }

  const manifest: unknown = JSON.parse(data.toString("utf8"));

  if (
    !isRecord(manifest) ||
    manifest.schemaVersion !== 1 ||
    manifest.archiveId !== event.archiveId ||
    !isNonEmptyString(manifest.createdAt) ||
    !Number.isFinite(Date.parse(manifest.createdAt)) ||
    !Array.isArray(manifest.snapshots) ||
    !manifest.snapshots.every(isManifestSnapshot) ||
    new Set(manifest.snapshots.map(({ snapshotId }) => snapshotId)).size !==
      manifest.snapshots.length ||
    (manifest.collectionId !== undefined &&
      typeof manifest.collectionId !== "string")
  ) {
    throw new Error("archive manifest does not match the v1 manifest contract");
  }

  return manifest as unknown as ManifestDocument;
}

async function processCrawlCompleted(
  event: CrawlCompletedEvent,
  reader: ArtifactObjectReader,
  manifestLedger: ManifestLedger,
  indexing: ProcessPageCapturedDependencies,
): Promise<void> {
  const data = await readArtifact(reader, event.manifest);
  const manifest = parseManifest(data, event);

  await manifestLedger.record({
    archiveId: manifest.archiveId,
    manifestDigest: event.manifestDigest,
    collectionId: manifest.collectionId ?? "",
    snapshotIds: manifest.snapshots.map(({ snapshotId }) => snapshotId),
  });

  for (const snapshot of manifest.snapshots) {
    await processPageCaptured(
      {
        messageId: `manifest:${event.manifestDigest}:${snapshot.snapshotId}`,
        correlationId: manifest.archiveId,
        occurredAt: manifest.createdAt,
        payload: {
          archiveId: manifest.archiveId,
          snapshotId: snapshot.snapshotId,
          urlKey: snapshot.urlKey,
          url: snapshot.url,
          finalUrl: snapshot.finalUrl,
          redirectChain:
            snapshot.redirectChain ?? [snapshot.url, snapshot.finalUrl],
          capturedAt: snapshot.capturedAt,
          ...(snapshot.contentType === undefined
            ? {}
            : { contentType: snapshot.contentType }),
          warcArtifacts: snapshot.warcArtifacts,
        },
      },
      indexing,
    );
  }
}

export { processCrawlCompleted };
export type { CrawlCompletedEvent };
