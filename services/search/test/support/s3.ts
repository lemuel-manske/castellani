import { randomUUID } from "node:crypto";
import {
  CreateBucketCommand,
  DeleteBucketCommand,
  DeleteObjectCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { createS3ArtifactReader } from "../../src/adapters/artifacts/s3.js";

import type { SearchSettings } from "../../src/config.js";

function createS3TestSupport(settings: SearchSettings) {
  const client = new S3Client({
    region: settings.awsRegion,
    endpoint: settings.s3EndpointUrl,
    credentials: {
      accessKeyId: settings.awsAccessKeyId,
      secretAccessKey: settings.awsSecretAccessKey,
    },
    forcePathStyle: true,
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

export { createS3TestSupport };
