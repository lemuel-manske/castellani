import { createHash } from "node:crypto";
import { expect, it, afterAll, beforeAll } from "vitest";
import {
  SEARCH_S3_ENDPOINT_URL,
  createS3TestSupport,
} from "../support/s3.js";

const support = createS3TestSupport();
const artifactBytes = Buffer.from("captured artifact payload");
const artifact = {
  bucket: support.bucketName,
  key: support.artifactKey,
  sha256: createHash("sha256").update(artifactBytes).digest("hex"),
  sizeBytes: artifactBytes.byteLength,
};

beforeAll(async () => {
  if (!SEARCH_S3_ENDPOINT_URL?.trim()) {
    throw new Error(
      "SEARCH_S3_ENDPOINT_URL is required; start the Search Compose dependencies and configure the integration-test environment",
    );
  }

  await support.setup();
  await support.putObject(artifactBytes);
});

afterAll(async () => {
  if (SEARCH_S3_ENDPOINT_URL?.trim()) {
    await support.teardown();
  }
});

it("reads the referenced object from the real S3-compatible service", async () => {
  const chunks = await Array.fromAsync(await support.reader.getObject(artifact));
  const result = Buffer.concat(chunks.map((chunk) => Buffer.from(chunk)));

  expect(result).toEqual(artifactBytes);
});
