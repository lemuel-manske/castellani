import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import type {
  ArtifactObjectReader,
  ArtifactReference,
} from "../../ports/artifacts.js";

function createS3ArtifactReader(client: S3Client): ArtifactObjectReader {
  return {
    async getObject(reference: ArtifactReference) {
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
        throw new Error(
          `S3 returned an empty body for ${reference.bucket}/${reference.key}`,
        );
      }

      return result.Body as AsyncIterable<Uint8Array>;
    },
  };
}

export { createS3ArtifactReader };
