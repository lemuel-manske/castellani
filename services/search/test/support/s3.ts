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
const ARTIFACT_KEY = "integration-artifact.warc.gz";

function createS3TestSupport() {
  const client = new S3Client({
    region: "us-east-1",
    endpoint: SEARCH_S3_ENDPOINT_URL ?? "http://localhost:9000",
    forcePathStyle: true,
    credentials: { accessKeyId: "minio", secretAccessKey: "minio-secret" },
  });
  const bucketName = `search-integration-${randomUUID().replaceAll("-", "")}`;

  return {
    client,
    bucketName,
    artifactKey: ARTIFACT_KEY,
    reader: createS3ArtifactReader(client),
    async setup(): Promise<void> {
      await client.send(new CreateBucketCommand({ Bucket: bucketName }));
    },
    async putObject(body: Uint8Array): Promise<void> {
      await client.send(
        new PutObjectCommand({
          Bucket: bucketName,
          Key: ARTIFACT_KEY,
          Body: body,
        }),
      );
    },
    async teardown(): Promise<void> {
      try {
        await client.send(
          new DeleteObjectCommand({
            Bucket: bucketName,
            Key: ARTIFACT_KEY,
          }),
        );
        await client.send(new DeleteBucketCommand({ Bucket: bucketName }));
      } finally {
        client.destroy();
      }
    },
  };
}

export { SEARCH_S3_ENDPOINT_URL, createS3TestSupport };
