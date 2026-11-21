import { createHash } from "node:crypto";

import { GetObjectCommand, NoSuchKey, type S3Client } from "@aws-sdk/client-s3";

import { type ArtifactRef, type ArtifactStore, DocumentError, UnsupportedContentError } from "./model.js";

export class S3ArtifactStore implements ArtifactStore {
  constructor(
    private readonly client: S3Client,
    private readonly maxBytes: number,
  ) {}

  async read(ref: ArtifactRef): Promise<Uint8Array> {
    if (ref.sizeBytes > this.maxBytes) {
      throw new UnsupportedContentError(
        `artifact s3://${ref.bucket}/${ref.key} is ${ref.sizeBytes} bytes, above the ${this.maxBytes} byte limit`,
      );
    }

    let bytes: Uint8Array;

    try {
      const object = await this.client.send(
        new GetObjectCommand({
          Bucket: ref.bucket,
          Key: ref.key,
          ...(ref.versionId ? { VersionId: ref.versionId } : {}),
        }),
      );

      if (object.Body === undefined) {
        throw new Error(`empty body for s3://${ref.bucket}/${ref.key}`);
      }

      bytes = await object.Body.transformToByteArray();
    } catch (error) {
      // A missing immutable artifact will not appear later; anything else
      // (network, throttling, emulator restart) is treated as transient.
      if (error instanceof NoSuchKey) {
        throw new DocumentError(`artifact s3://${ref.bucket}/${ref.key} does not exist`);
      }

      throw error;
    }

    verify(ref, bytes);

    return bytes;
  }
}

export function verify(ref: ArtifactRef, bytes: Uint8Array): void {
  if (bytes.byteLength !== ref.sizeBytes) {
    throw new DocumentError(
      `artifact s3://${ref.bucket}/${ref.key} has ${bytes.byteLength} bytes, expected ${ref.sizeBytes}`,
    );
  }

  const digest = createHash("sha256").update(bytes).digest("hex");

  if (digest !== ref.sha256) {
    throw new DocumentError(`artifact s3://${ref.bucket}/${ref.key} failed SHA-256 verification`);
  }
}
