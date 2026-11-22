import { Readable } from "node:stream";
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

  const chunks = await Readable.from<Uint8Array>(
    await s3.reader.getObject(fixture.artifact),
  ).toArray() as Uint8Array[];

  expect(Buffer.concat(chunks.map((chunk) => Buffer.from(chunk)))).toEqual(
    fixture.bytes,
  );
});
