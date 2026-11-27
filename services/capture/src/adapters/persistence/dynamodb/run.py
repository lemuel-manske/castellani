from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

from domain.capture import StartCrawl, capture_page_message_id, identify_url
from ports.capture import CrawlStarter
from ports.clock import Clock

from .error_handling import extract_cancellation_reasons, raise_unless_transaction_canceled
from .queries.common import transact_write_items
from .queries.run import seed_run_transaction
from .queries.task import read_run

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient


class DynamoDBRunStarter(CrawlStarter):
    """Seeds a crawl run, its seed page, and the first CapturePage outbox record."""

    def __init__(
        self,
        client: DynamoDBClient,
        clock: Clock = time.time,
    ) -> None:
        self.client = client
        self.clock = clock

    async def __call__(self, start: StartCrawl) -> None:
        def do_start() -> None:
            now = self.clock()

            identity = identify_url(start.seed_url)
            message_id = capture_page_message_id(start.archive_id, identity.url_key)

            try:
                transact_write_items(
                    self.client,
                    seed_run_transaction(start, message_id, now),
                )
            except ClientError as error:
                raise_unless_transaction_canceled(error)

                if "ConditionalCheckFailed" not in extract_cancellation_reasons(error):
                    raise

                if read_run(self.client, start.archive_id) is None:
                    raise

        await asyncio.to_thread(do_start)
