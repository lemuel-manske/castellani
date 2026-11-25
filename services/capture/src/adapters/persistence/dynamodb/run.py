import asyncio
import time
from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from botocore.exceptions import ClientError

from domain.capture import StartCrawl, identify_url
from domain.capture.crawl import CrawlStarter

from .error_handling import extract_cancellation_reasons, is_transaction_canceled
from .queries.run import seed_run_transaction
from .queries.task import read_run


class DynamoDBRunStarter(CrawlStarter):
    """Seeds a crawl run, its seed page, and the first CapturePage outbox record."""

    def __init__(
        self,
        client: Any,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.client = client
        self.clock = clock

    async def __call__(self, start: StartCrawl) -> None:
        def do_start() -> None:
            now = self.clock()

            identity = identify_url(start.seed_url)
            message_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"capture-page:{start.archive_id}:{identity.url_key}",
                )
            )

            try:
                self.client.transact_write_items(
                    TransactItems=seed_run_transaction(start, message_id, now),
                )
            except ClientError as error:
                if not is_transaction_canceled(error):
                    raise

                if "ConditionalCheckFailed" not in extract_cancellation_reasons(error):
                    raise

                if read_run(self.client, start.archive_id) is None:
                    raise

        await asyncio.to_thread(do_start)
