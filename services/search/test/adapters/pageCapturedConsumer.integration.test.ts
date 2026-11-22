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
