import { expect, it } from "vitest";
import {
  s3,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import { createCapturedPageFixture } from "../support/fixtures.js";

setupIntegrationEnvironment("s3");

it("reads the referenced object from the real S3-compatible service", async () => {
  const fixture = createCapturedPageFixture("s3-read", {
    bucket: s3.bucketName,
  });
  await s3.putObject(fixture.bytes, fixture.artifact.key);

  const chunks: Uint8Array[] = [];
  for await (const chunk of await s3.reader.getObject(fixture.artifact)) {
    chunks.push(chunk);
  }

  expect(Buffer.concat(chunks.map((chunk) => Buffer.from(chunk)))).toEqual(
    fixture.bytes,
  );
});
