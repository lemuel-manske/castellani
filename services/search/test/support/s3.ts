import { randomUUID } from "node:crypto";
import {
  CreateBucketCommand,
  DeleteBucketCommand,
  DeleteObjectCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { createS3ArtifactReader } from "../../src/adapters/artifacts/s3.js";

const SEARCH_S3_ENDPOINT_URL = process.env.SEARCH_S3_ENDPOINT_URL;

function createS3TestSupport() {
  const client = new S3Client({
    region: "us-east-1",
    endpoint: SEARCH_S3_ENDPOINT_URL ?? "http://localhost:9000",
    forcePathStyle: true,
    credentials: { accessKeyId: "minio", secretAccessKey: "minio-secret" },
  });
  const bucketName = `search-integration-${randomUUID().replaceAll("-", "")}`;
  const objectKeys = new Set<string>();

  return {
    client,
    bucketName,
    reader: createS3ArtifactReader(client),
    async setup(): Promise<void> {
      await client.send(new CreateBucketCommand({ Bucket: bucketName }));
    },
    async putObject(body: Uint8Array, key: string): Promise<void> {
      await client.send(
        new PutObjectCommand({ Bucket: bucketName, Key: key, Body: body }),
      );
      objectKeys.add(key);
    },
    async teardown(): Promise<void> {
      try {
        await Promise.all(
          [...objectKeys].map((key) =>
            client.send(
              new DeleteObjectCommand({ Bucket: bucketName, Key: key }),
            ),
          ),
        );
        await client.send(new DeleteBucketCommand({ Bucket: bucketName }));
      } finally {
        client.destroy();
      }
    },
  };
}

export { SEARCH_S3_ENDPOINT_URL, createS3TestSupport };
