import { randomUUID } from "node:crypto";
import { expect, it } from "vitest";

import { PAGE_CAPTURED_EVENT } from "../../src/domain.js";
import { createCapturedPageFixture } from "../support/fixtures.js";
import {
  nextPageCaptured,
  opensearch,
  rabbitmq,
  s3,
  searchIndex,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";

setupIntegrationEnvironment(["dynamodb", "opensearch", "rabbitmq", "s3"]);

it("indexes a captured page delivered through RabbitMQ from its WARC artifact", async () => {
  const token = randomUUID().replaceAll("-", "");

  const snapshotId = `rabbitmq-warc-${token}`;
  const content = `Integrated content ${token}`;

  const fixture = createCapturedPageFixture(snapshotId, {
    bucket: s3.bucketName,
    body: `<html><head><title>${content}</title></head><body><h1>${content}</h1></body></html>`,
  });

  await s3.putObject(fixture.bytes, fixture.artifact.key);
  await rabbitmq.publish(fixture.event);

  const event = await nextPageCaptured();

  expect(event).toMatchObject({
    type: PAGE_CAPTURED_EVENT,
    messageId: fixture.event.messageId,
    payload: {
      archiveId: fixture.event.payload.archiveId,
      snapshotId: fixture.event.payload.snapshotId,
    },
  });

  await opensearch.client.indices.refresh();

  const indexed = await searchIndex.search({ text: token }, 10);

  expect(indexed.candidates).toMatchObject([
    {
      document: {
        archiveId: fixture.event.payload.archiveId,
        snapshotId: fixture.event.payload.snapshotId,
        url: fixture.event.payload.url,
        finalUrl: fixture.event.payload.finalUrl,
        title: content,
      },
    },
  ]);

  expect(indexed.nextCursor).toBeNull();
});
