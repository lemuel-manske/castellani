import { afterAll, beforeAll } from "vitest";

import {
  ARCHIVE_COMPENSATION_DECIDED_EVENT,
  CRAWL_COMPLETED_EVENT,
  type CompensationDecision,
  type CompletionCrawl,
} from "../../src/domain.js";
import type { PublicationEvent } from "../../src/application/processPublicationEvent.js";
import type { Event } from "../../src/application/types.js";
import { dispatchOutbox as dispatchOutboxEvents } from "../../src/application/dispatchOutbox.js";
import { processCrawlCompleted } from "../../src/application/processCrawlCompleted.js";
import { processPageCaptured } from "../../src/application/processPageCaptured.js";
import { processPublicationEvent } from "../../src/application/processPublicationEvent.js";
import { reportArchiveEvents } from "../../src/application/reportArchiveEvents.js";
import { searchPublishedDocuments } from "../../src/application/searchPublishedDocuments.js";
import type {
  PageCapturedEvent,
  PageCapturedResult,
  SearchPublishedDocumentsInput,
} from "../../src/application/types.js";

import type { SearchQuery } from "../../src/ports/search-reader.js";

import { createRabbitMQEventsPublisher } from "../../src/adapters/messaging/rabbitmq/eventsPublisher.js";
import { createOpenSearchDocumentReader } from "../../src/adapters/search/opensearch-reader.js";
import { createOpenSearchDocumentWriter } from "../../src/adapters/search/opensearch.js";
import { createS3ArtifactReader } from "../../src/adapters/artifacts/s3.js";
import { createWarcCapturedPageReader } from "../../src/adapters/artifacts/warc.js";

import { createDynamoDbTestSupport } from "./dynamoDb.js";
import { createOpenSearchTestSupport } from "./openSearch.js";
import { createRabbitMqTestSupport } from "./rabbitMq.js";
import { createS3TestSupport } from "./s3.js";

import {
  SEARCH_DYNAMODB_ENDPOINT_URL,
  SEARCH_OPENSEARCH_URL,
  SEARCH_RABBITMQ_URL,
  SEARCH_S3_ENDPOINT_URL,
} from "./env.js";

const INDEXING_LEASE_DURATION_SECONDS = 120;
const INDEXING_MAX_ATTEMPTS = 5;

const dynamodb = createDynamoDbTestSupport();
const opensearch = createOpenSearchTestSupport();
const rabbitmq = createRabbitMqTestSupport();
const s3 = createS3TestSupport();

const artifactReader = createS3ArtifactReader(s3.client);
const capturedPageReader = createWarcCapturedPageReader(artifactReader);
const documentReader = createOpenSearchDocumentReader(opensearch.client);
const documentWriter = createOpenSearchDocumentWriter(opensearch.client);
const eventsPublisher = createRabbitMQEventsPublisher(
  SEARCH_RABBITMQ_URL ?? "amqp://localhost",
);

const compensationDecisions: CompensationDecision[] = [];

function report(archiveId: string): Promise<void> {
  return reportArchiveEvents(
    archiveId,
    dynamodb.ledger,
    dynamodb.manifestLedger,
    dynamodb.publicationLedger,
  );
}

const application = {
  async processPageCaptured(
    event: PageCapturedEvent,
  ): Promise<PageCapturedResult> {
    const result = await processPageCaptured(
      event,
      dynamodb.ledger,
      capturedPageReader,
      documentWriter,
      INDEXING_LEASE_DURATION_SECONDS,
      INDEXING_MAX_ATTEMPTS,
      dynamodb.publicationLedger,
    );

    if (result.status === "COMPLETED") {
      await report(event.payload.archiveId);
    }

    return result;
  },

  async processCrawlCompleted(
    event: Event<typeof CRAWL_COMPLETED_EVENT, CompletionCrawl>,
  ): Promise<void> {
    await processCrawlCompleted(
      event,
      artifactReader,
      dynamodb.manifestLedger,
      dynamodb.ledger,
      capturedPageReader,
      documentWriter,
      INDEXING_LEASE_DURATION_SECONDS,
      INDEXING_MAX_ATTEMPTS,
      dynamodb.publicationLedger,
    );

    await report(event.payload.archiveId);
  },

  async processPublicationEvent(
    event: Exclude<PublicationEvent, { type: typeof CRAWL_COMPLETED_EVENT }>,
  ): Promise<void> {
    if (event.type === ARCHIVE_COMPENSATION_DECIDED_EVENT) {
      compensationDecisions.push(event.payload);
    }

    await processPublicationEvent(
      event,
      dynamodb.publicationLedger,
      documentWriter,
    );

    await report(event.payload.archiveId);
  },

  async drainOutbox(): Promise<void> {
    while (
      await dispatchOutboxEvents(
        dynamodb.outbox,
        documentWriter,
        eventsPublisher,
      )
    ) {
      // Drain every outbox entry recorded by the current test.
    }
  },

  report(archiveId: string): Promise<void> {
    return report(archiveId);
  },

  searchPublishedDocuments(input: SearchPublishedDocumentsInput) {
    return searchPublishedDocuments(
      input,
      documentReader,
      dynamodb.publicationLedger,
      dynamodb.manifestLedger,
    );
  },
};

// Raw index inspection is kept in integration support so tests do not compose adapters.
const searchIndex = {
  search(query: SearchQuery, limit: number) {
    return documentReader.search(query, limit);
  },
};

const deliveries: PageCapturedEvent[] = [];
const publicationDeliveries: PublicationEvent[] = [];

const deliveryWaiters: ((event: PageCapturedEvent) => void)[] = [];
const publicationDeliveryWaiters: ((event: PublicationEvent) => void)[] = [];

let publicationLedgerReady = false;

async function receivePageCaptured(
  event: PageCapturedEvent,
): Promise<PageCapturedResult> {
  const result = await application.processPageCaptured(event);
  const waiter = deliveryWaiters.shift();

  if (waiter) {
    waiter(event);
  } else {
    deliveries.push(event);
  }

  return result;
}

async function receivePublicationEvent(event: PublicationEvent): Promise<void> {
  if (publicationLedgerReady && event.type === CRAWL_COMPLETED_EVENT) {
    await application.processCrawlCompleted(event);
  }

  if (publicationLedgerReady && event.type !== CRAWL_COMPLETED_EVENT) {
    await application.processPublicationEvent(event);
  }

  const waiter = publicationDeliveryWaiters.shift();

  if (waiter) {
    waiter(event);
  } else {
    publicationDeliveries.push(event);
  }
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
    setup: async () => {
      await rabbitmq.setup(receivePageCaptured, receivePublicationEvent);
      await rabbitmq.startEventsObserver();
    },
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
      publicationLedgerReady ||= service === "dynamodb";
    }
  });

  afterAll(async () => {
    await Promise.allSettled(
      [...selected]
        .reverse()
        .map((service) => integrations[service].teardown()),
    );
    publicationLedgerReady = false;
  });
}

export {
  application,
  compensationDecisions,
  dynamodb,
  nextPageCaptured,
  nextPublicationEvent,
  opensearch,
  rabbitmq,
  s3,
  searchIndex,
  setupIntegrationEnvironment,
};
