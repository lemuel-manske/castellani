import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { PageCapturedEvent } from "../../src/application/processPageCaptured.js";
import {
  SEARCH_RABBITMQ_URL,
  createRabbitMqTestSupport,
} from "../support/rabbitMq.js";
import { createPageCapturedEvent } from "../support/pageCaptured.js";

describe.skipIf(!SEARCH_RABBITMQ_URL)("RabbitMQ integration", () => {
  const support = createRabbitMqTestSupport();
  let delivered: Promise<PageCapturedEvent>;
  let resolveDelivery!: (event: PageCapturedEvent) => void;

  beforeAll(async () => {
    delivered = new Promise((resolve) => {
      resolveDelivery = resolve;
    });

    await support.setup(async (event) => {
      resolveDelivery(event);
    });
  });

  afterAll(async () => {
    await support.teardown();
  });

  it("delivers a published PageCaptured event to the real consumer", async () => {
    const event = createPageCapturedEvent("integration-message");

    await support.publish(event);

    await expect(delivered).resolves.toMatchObject({
      messageId: "integration-message",
      correlationId: "integration-archive",
      payload: {
        archiveId: "integration-archive",
        snapshotId: "integration-snapshot",
      },
    });
  });
});
