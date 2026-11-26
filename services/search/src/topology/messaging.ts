import { PAGE_CAPTURED_EVENT } from "../domain/index.js";

const EVENTS_EXCHANGE = "castellani.events";

const PAGE_CAPTURED_TOPOLOGY = {
  routingKey: PAGE_CAPTURED_EVENT,
  queue: "castellani.search.page-captured",
  retryExchange: "castellani.search.retry",
  retryQueue: "castellani.search.page-captured.retry",
  deadLetterExchange: "castellani.search.dead",
  deadLetterQueue: "castellani.search.page-captured.dead",
} as const;

const PUBLICATION_TOPOLOGY = {
  queue: "castellani.search.publication",
  retryExchange: "castellani.search.publication.retry",
  retryQueue: "castellani.search.publication.retry.queue",
  deadLetterExchange: "castellani.search.publication.dead",
  deadLetterQueue: "castellani.search.publication.dead.queue",
} as const;

export { EVENTS_EXCHANGE, PAGE_CAPTURED_TOPOLOGY, PUBLICATION_TOPOLOGY };
