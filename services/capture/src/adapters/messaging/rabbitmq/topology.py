CAPTURE_EXCHANGE_NAME = "castellani.capture"
EVENTS_EXCHANGE_NAME = "castellani.events"

CAPTURE_PAGE_EVENT = "CapturePage"
PAGE_CAPTURED_EVENT = "PageCaptured"
CRAWL_COMPLETED_EVENT = "CrawlCompleted"
START_CRAWL_EVENT = "StartCrawl"

CAPTURE_DEAD_EXCHANGE = "castellani.capture.dead"

CAPTURE_DEAD_QUEUE = "castellani.capture.dead"
CAPTURE_PAGE_QUEUE = "castellani.capture.page"
PAGE_CAPTURED_QUEUE = "castellani.search.page-captured"
CRAWL_COMPLETED_QUEUE = "castellani.coordinator"
CAPTURE_PAGE_RETRY_QUEUE = "castellani.capture.page.retry"
START_CRAWL_QUEUE = "castellani.capture.start"
START_CRAWL_RETRY_QUEUE = "castellani.capture.start.retry"

MESSAGE_VERSION = 1
MAX_DELIVERY_RETRIES = 5
