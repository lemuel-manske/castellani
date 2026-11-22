import { afterAll, beforeAll } from "vitest";
import type { PageCapturedEvent } from "../../src/application/processPageCaptured.js";
import type { PublicationEvent } from "../../src/application/processPublicationEvent.js";
import {
  SEARCH_DYNAMODB_ENDPOINT_URL,
  createDynamoDbTestSupport,
} from "./dynamoDb.js";
import {
  SEARCH_OPENSEARCH_URL,
  createOpenSearchTestSupport,
} from "./openSearch.js";
import { SEARCH_RABBITMQ_URL, createRabbitMqTestSupport } from "./rabbitMq.js";
import { SEARCH_S3_ENDPOINT_URL, createS3TestSupport } from "./s3.js";

const clock = { now: 1_000_000 };
const dynamodb = createDynamoDbTestSupport(() => clock.now);
const opensearch = createOpenSearchTestSupport();
const rabbitmq = createRabbitMqTestSupport();
const s3 = createS3TestSupport();
const deliveries: PageCapturedEvent[] = [];
const deliveryWaiters: ((event: PageCapturedEvent) => void)[] = [];
const publicationDeliveries: PublicationEvent[] = [];
const publicationDeliveryWaiters: ((event: PublicationEvent) => void)[] = [];

function receivePageCaptured(event: PageCapturedEvent): Promise<void> {
  const waiter = deliveryWaiters.shift();

  if (waiter) {
    waiter(event);
  } else {
    deliveries.push(event);
  }

  return Promise.resolve();
}

function receivePublicationEvent(event: PublicationEvent): Promise<void> {
  const waiter = publicationDeliveryWaiters.shift();

  if (waiter) {
    waiter(event);
  } else {
    publicationDeliveries.push(event);
  }

  return Promise.resolve();
}

function nextPageCaptured(): Promise<PageCapturedEvent> {
  const event = deliveries.shift();

  if (event) {
    return Promise.resolve(event);
  }

  return new Promise((resolve) => deliveryWaiters.push(resolve));
}

function nextPublicationEvent(): Promise<PublicationEvent> {
  const event = publicationDeliveries.shift();

  if (event) {
    return Promise.resolve(event);
  }

  return new Promise((resolve) => publicationDeliveryWaiters.push(resolve));
}

const integrations = {
  dynamodb: {
    endpoint: SEARCH_DYNAMODB_ENDPOINT_URL,
    setup: () => dynamodb.setup(),
    teardown: () => dynamodb.teardown(),
  },
  opensearch: {
    endpoint: SEARCH_OPENSEARCH_URL,
    setup: () => opensearch.setup(),
    teardown: () => opensearch.teardown(),
  },
  rabbitmq: {
    endpoint: SEARCH_RABBITMQ_URL,
    setup: () => rabbitmq.setup(receivePageCaptured, receivePublicationEvent),
    teardown: () => rabbitmq.teardown(),
  },
  s3: {
    endpoint: SEARCH_S3_ENDPOINT_URL,
    setup: () => s3.setup(),
    teardown: () => s3.teardown(),
  },
};

type IntegrationService = keyof typeof integrations;

function setupIntegrationEnvironment(
  services: IntegrationService | readonly IntegrationService[],
): void {
  const selected = typeof services === "string" ? [services] : [...services];

  beforeAll(async () => {
    const missing = selected.filter(
      (service) => !integrations[service].endpoint?.trim(),
    );

    if (missing.length > 0) {
      throw new Error(
        `Missing integration-test endpoints for: ${missing.join(", ")}. Start the required Search Compose dependencies and use the integration-test Make target.`,
      );
    }

    for (const service of selected) {
      await integrations[service].setup();
    }
  });

  afterAll(async () => {
    await Promise.allSettled(
      [...selected]
        .reverse()
        .map((service) => integrations[service].teardown()),
    );
  });
}

export {
  clock,
  dynamodb,
  nextPageCaptured,
  nextPublicationEvent,
  opensearch,
  rabbitmq,
  s3,
  setupIntegrationEnvironment,
};
