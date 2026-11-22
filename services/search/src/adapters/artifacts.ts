import { createHash } from "node:crypto";
import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { WARCParser } from "warcio";
import type { CapturedPage } from "../domain/content.js";

interface ArtifactReference {
  bucket: string;
  key: string;
  versionId?: string;
  sha256: string;
  sizeBytes: number;
}

interface CapturedPageReference {
  archiveId: string;
  snapshotId: string;
  url: string;
  finalUrl?: string;
  capturedAt: string;
  contentType?: string;
}

interface ArtifactObjectReader {
  getObject(reference: ArtifactReference): Promise<AsyncIterable<Uint8Array>>;
}

class ArtifactIntegrityError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ArtifactIntegrityError";
  }
}

class CapturedResponseNotFoundError extends Error {
  constructor(snapshotId: string) {
    super(`no WARC response found for snapshot ${snapshotId}`);
    this.name = "CapturedResponseNotFoundError";
  }
}

async function* verifiedChunks(
  body: AsyncIterable<Uint8Array>,
  reference: ArtifactReference,
): AsyncGenerator<Uint8Array> {
  const digest = createHash("sha256");
  let sizeBytes = 0;

  for await (const chunk of body) {
    digest.update(chunk);
    sizeBytes += chunk.byteLength;
    yield chunk;
  }

  if (sizeBytes !== reference.sizeBytes) {
    throw new ArtifactIntegrityError(
      `artifact size mismatch for ${reference.bucket}/${reference.key}`,
    );
  }

  if (digest.digest("hex") !== reference.sha256) {
    throw new ArtifactIntegrityError(
      `artifact checksum mismatch for ${reference.bucket}/${reference.key}`,
    );
  }
}

async function readWarcArtifact(
  reference: ArtifactReference,
  page: CapturedPageReference,
  reader: ArtifactObjectReader,
): Promise<{ content: string; contentType: string } | null> {
  const body = await reader.getObject(reference);
  const parser = new WARCParser(verifiedChunks(body, reference));
  let requestedUrlResponse: { content: string; contentType: string } | null = null;

  for await (const record of parser) {
    if (record.warcType !== "response") {
      continue;
    }

    const target = record.warcTargetURI;

    if (target !== page.url && target !== (page.finalUrl ?? page.url)) {
      continue;
    }

    const response = record.getResponseInfo();
    const candidate = {
      content: await record.contentText(),
      contentType:
        response.headers.get("content-type") ??
        page.contentType ??
        "application/octet-stream",
    };

    if (target === (page.finalUrl ?? page.url)) {
      return candidate;
    }

    requestedUrlResponse = candidate;
  }

  return requestedUrlResponse;
}

async function readCapturedPage(
  page: CapturedPageReference,
  artifacts: readonly ArtifactReference[],
  reader: ArtifactObjectReader,
): Promise<CapturedPage> {
  if (artifacts.length === 0) {
    throw new ArtifactIntegrityError(
      `snapshot ${page.snapshotId} has no WARC artifact references`,
    );
  }

  let requestedUrlResponse: { content: string; contentType: string } | null = null;

  for (const artifact of artifacts) {
    const response = await readWarcArtifact(artifact, page, reader);

    if (response === null) {
      continue;
    }

    if (response.contentType && page.finalUrl && page.finalUrl !== page.url) {
      return {
        archiveId: page.archiveId,
        snapshotId: page.snapshotId,
        url: page.url,
        finalUrl: page.finalUrl,
        capturedAt: page.capturedAt,
        contentType: response.contentType,
        content: response.content,
      };
    }

    requestedUrlResponse = response;
  }

  const response = requestedUrlResponse;

  if (response === null) {
    throw new CapturedResponseNotFoundError(page.snapshotId);
  }

  return {
    archiveId: page.archiveId,
    snapshotId: page.snapshotId,
    url: page.url,
    finalUrl: page.finalUrl ?? page.url,
    capturedAt: page.capturedAt,
    contentType: response.contentType,
    content: response.content,
  };
}

function createS3ArtifactReader(client: S3Client): ArtifactObjectReader {
  return {
    async getObject(reference) {
      const result = await client.send(
        new GetObjectCommand({
          Bucket: reference.bucket,
          Key: reference.key,
          ...(reference.versionId === undefined
            ? {}
            : { VersionId: reference.versionId }),
        }),
      );

      if (result.Body === undefined) {
        throw new ArtifactIntegrityError(
          `S3 returned an empty body for ${reference.bucket}/${reference.key}`,
        );
      }

      return result.Body as AsyncIterable<Uint8Array>;
    },
  };
}

export {
  ArtifactIntegrityError,
  CapturedResponseNotFoundError,
  createS3ArtifactReader,
  readCapturedPage,
};
export type { ArtifactObjectReader, ArtifactReference, CapturedPageReference };
