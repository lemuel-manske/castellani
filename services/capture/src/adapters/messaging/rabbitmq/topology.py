"""Broker names used by Capture. The resources are provisioned by infra/rabbitmq."""

CAPTURE_EXCHANGE_NAME = "castellani.capture"
EVENTS_EXCHANGE_NAME = "castellani.events"
CAPTURE_RETRY_EXCHANGE = "castellani.capture.retry"
CAPTURE_DEAD_EXCHANGE = "castellani.capture.dead"

CAPTURE_PAGE_EVENT = "CapturePage"
CAPTURE_PAGE_QUEUE = "castellani.capture.page"
CAPTURE_PAGE_RETRY_QUEUE = "castellani.capture.page.retry"

START_CRAWL_EVENT = "StartCrawl"
START_CRAWL_QUEUE = "castellani.capture.start"
START_CRAWL_RETRY_QUEUE = "castellani.capture.start.retry"

CAPTURE_DEAD_QUEUE = "castellani.capture.dead"

MESSAGE_VERSION = 1
MAX_DELIVERY_ATTEMPTS = 5
