const EVENTS_EXCHANGE = "castellani.events";

const PAGE_CAPTURED_TOPOLOGY = {
  routingKey: "PageCaptured",
  queue: "castellani.search.page-captured",
  retryExchange: "castellani.search.retry",
  retryQueue: "castellani.search.page-captured.retry",
  deadLetterExchange: "castellani.search.dead",
  deadLetterQueue: "castellani.search.page-captured.dead",
  retryDelayMilliseconds: 5_000,
} as const;

const PUBLICATION_TOPOLOGY = {
  routingKeys: [
    "ArchivePublicationDecided",
    "ArchivePublished",
    "ArchiveCompensationDecided",
    "CrawlCompleted",
  ],
  queue: "castellani.search.publication",
  retryExchange: "castellani.search.publication.retry",
  retryQueue: "castellani.search.publication.retry.queue",
  deadLetterExchange: "castellani.search.publication.dead",
  deadLetterQueue: "castellani.search.publication.dead.queue",
  retryDelayMilliseconds: 5_000,
} as const;

export { EVENTS_EXCHANGE, PAGE_CAPTURED_TOPOLOGY, PUBLICATION_TOPOLOGY };
