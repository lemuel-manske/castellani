import { expect, it } from "vitest";

import { createOpenSearchDocumentReader } from "../../src/adapters/search/opensearch-reader.js";
import { createOpenSearchDocumentWriter } from "../../src/adapters/search/opensearch.js";
import { createWarcCapturedPageReader } from "../../src/adapters/artifacts/warc.js";
import { processPageCaptured } from "../../src/application/processPageCaptured.js";

import { createCapturedPageFixture } from "../support/fixtures.js";
import {
  dynamodb,
  nextPageCaptured,
  opensearch,
  rabbitmq,
  s3,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";

setupIntegrationEnvironment(["dynamodb", "opensearch", "rabbitmq", "s3"]);

it("indexes a captured page delivered through RabbitMQ from its WARC artifact", async () => {
  const fixture = createCapturedPageFixture("rabbitmq-warc-snapshot", {
    bucket: s3.bucketName,
  });

  await s3.putObject(fixture.bytes, fixture.artifact.key);
  await rabbitmq.publish(fixture.event);

  const event = await nextPageCaptured();

  expect(event).toMatchObject({
    type: "PageCaptured",
    messageId: fixture.event.messageId,
    payload: {
      archiveId: fixture.event.payload.archiveId,
      snapshotId: fixture.event.payload.snapshotId,
    },
  });

  const result = await processPageCaptured(
    event,
    dynamodb.ledger,
    createWarcCapturedPageReader(s3.reader),
    createOpenSearchDocumentWriter(opensearch.client, opensearch.indexName),
  );

  expect(result).toEqual({
    status: "COMPLETED",
    outcome: "INDEXED",
  });

  await opensearch.client.indices.refresh({ index: opensearch.indexName });

  const indexed = await createOpenSearchDocumentReader(
    opensearch.client,
    opensearch.indexName,
  ).search({ text: "Integrated content" }, 10);

  expect(indexed.candidates).toMatchObject([
    {
      document: {
        archiveId: fixture.event.payload.archiveId,
        snapshotId: fixture.event.payload.snapshotId,
        url: fixture.event.payload.url,
        finalUrl: fixture.event.payload.finalUrl,
        title: "Integrated content",
      },
    },
  ]);
  expect(indexed.nextCursor).toBeNull();
});
