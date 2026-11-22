import { expect, it } from "vitest";
import {
  nextPageCaptured,
  rabbitmq,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import { createPageCapturedEvent } from "../support/pageCaptured.js";

setupIntegrationEnvironment("rabbitmq");

it("delivers a published PageCaptured event to the real consumer", async () => {
  const event = createPageCapturedEvent("integration-message");
  const delivered = nextPageCaptured();

  await rabbitmq.publish(event);

  await expect(delivered).resolves.toMatchObject({
    messageId: "integration-message",
    correlationId: "integration-archive",
    payload: {
      archiveId: "integration-archive",
      snapshotId: "integration-snapshot",
    },
  });
});


it("dead-letters malformed PageCaptured envelopes", async () => {
  const deadLetter = rabbitmq.nextDeadLetter();

  await rabbitmq.publish({ messageId: "malformed-message" });

  const message = await deadLetter;

  expect(message.content.toString("utf8")).toBe(
    JSON.stringify({ messageId: "malformed-message" }),
  );
});
