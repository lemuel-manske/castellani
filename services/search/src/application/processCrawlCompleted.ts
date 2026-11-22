import { createHash } from "node:crypto";
import type {
  ArtifactObjectReader,
  ArtifactReference,
} from "../ports/artifacts.js";
import type { ManifestLedger } from "../ports/manifest-ledger.js";
interface CrawlCompletedEvent {
  archiveId: string;
  manifestDigest: string;
  manifest: ArtifactReference;
}
interface ManifestDocument {
  schemaVersion: number;
  archiveId: string;
  collectionId?: string;
  snapshots: { snapshotId: string }[];
}

async function readArtifact(
  reader: ArtifactObjectReader,
  reference: ArtifactReference,
): Promise<Buffer> {
  const chunks: Buffer[] = [];

  for await (const chunk of await reader.getObject(reference))
    chunks.push(Buffer.from(chunk));

  const data = Buffer.concat(chunks);

  if (data.byteLength !== reference.sizeBytes)
    throw new Error(
      "archive manifest size does not match its immutable reference",
    );

  return data;
}
function parseManifest(
  data: Buffer,
  event: CrawlCompletedEvent,
): ManifestDocument {
  const digest = createHash("sha256").update(data).digest("hex");
  const expectedDigest = event.manifestDigest.replace(/^sha256:/, "");

  if (digest !== expectedDigest || digest !== event.manifest.sha256)
    throw new Error(
      "archive manifest digest does not match its immutable reference",
    );

  const manifest: unknown = JSON.parse(data.toString("utf8"));

  if (
    typeof manifest !== "object" ||
    manifest === null ||
    Array.isArray(manifest) ||
    !("schemaVersion" in manifest) ||
    manifest.schemaVersion !== 1 ||
    !("archiveId" in manifest) ||
    manifest.archiveId !== event.archiveId ||
    !("snapshots" in manifest) ||
    !Array.isArray(manifest.snapshots) ||
    !manifest.snapshots.every(
      (entry: unknown) =>
        typeof entry === "object" &&
        entry !== null &&
        "snapshotId" in entry &&
        typeof entry.snapshotId === "string" &&
        entry.snapshotId.length > 0,
    ) ||
    ("collectionId" in manifest && typeof manifest.collectionId !== "string")
  ) {
    throw new Error("archive manifest does not match the v1 manifest contract");
  }

  return manifest as ManifestDocument;
}
async function processCrawlCompleted(
  event: CrawlCompletedEvent,
  reader: ArtifactObjectReader,
  ledger: ManifestLedger,
): Promise<void> {
  const data = await readArtifact(reader, event.manifest);
  const manifest = parseManifest(data, event);

  await ledger.record({
    archiveId: manifest.archiveId,
    manifestDigest: event.manifestDigest,
    collectionId: manifest.collectionId ?? "",
    snapshotIds: manifest.snapshots.map(({ snapshotId }) => snapshotId),
  });
}
export { processCrawlCompleted };
export type { CrawlCompletedEvent };
