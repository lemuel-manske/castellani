import { afterAll, beforeAll, expect, it } from "vitest";
import type { PageCapturedEvent } from "../../src/application/processPageCaptured.js";
import {
  SEARCH_RABBITMQ_URL,
  createRabbitMqTestSupport,
} from "../support/rabbitMq.js";
import { createPageCapturedEvent } from "../support/pageCaptured.js";

const support = createRabbitMqTestSupport();
let delivered: Promise<PageCapturedEvent>;
let resolveDelivery!: (event: PageCapturedEvent) => void;

beforeAll(async () => {
  if (!SEARCH_RABBITMQ_URL?.trim()) {
    throw new Error(
      "SEARCH_RABBITMQ_URL is required; start the Search Compose dependencies and configure the integration-test environment",
    );
  }

  delivered = new Promise((resolve) => {
    resolveDelivery = resolve;
  });

  await support.setup(async (event) => {
    resolveDelivery(event);
  });
});

afterAll(async () => {
  if (SEARCH_RABBITMQ_URL?.trim()) {
    await support.teardown();
  }
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
