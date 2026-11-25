from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import aio_pika
import boto3
from aio_pika.abc import AbstractRobustConnection

from adapters.artifacts.auth import AuthProfileCipher, EncryptedAuthProfileStore
from adapters.artifacts.s3 import S3ArtifactStore
from adapters.browser.executor import BrowserPageExecutor
from adapters.messaging.rabbitmq.consumer import (
    RabbitMQPageTaskConsumer,
    RabbitMQStartCrawlConsumer,
)
from adapters.messaging.rabbitmq.publisher import RabbitMQMessagePublisher
from adapters.persistence.dynamodb.alloc import DynamoDBCaptureAllocator
from adapters.persistence.dynamodb.archive import DynamoDBArchiveRetrieval
from adapters.persistence.dynamodb.outbox import DynamoDBOutbox
from adapters.persistence.dynamodb.run import DynamoDBRunStarter
from adapters.persistence.dynamodb.session import DynamoDBSessionStore
from adapters.persistence.dynamodb.task import DynamoDBTaskRepository
from application.capture import OutboxDispatcher, StoredAuthContexts
from application.capture.page_tasks import PageTaskProcessor
from application.capture.start_crawls import StartCrawlProcessor
from topology.buckets import ARCHIVE_ARTIFACTS_BUCKET
from topology.tables import CAPTURE_TABLES

from .settings import CaptureSettings
from .worker import new_worker

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient
    from mypy_boto3_s3.client import S3Client

CONSUMER_START_TIMEOUT_SECONDS = 10

SHUTDOWN_TIMEOUT_SECONDS = 35


class CaptureRuntime:
    """Assembles and manages the Capture worker and messaging processes."""

    def __init__(self, settings: CaptureSettings) -> None:
        self.settings = settings

        self.dynamodb_client: DynamoDBClient | None = None
        self.s3_client: S3Client | None = None
        self.archive_retrieval: DynamoDBArchiveRetrieval | None = None

        self.connection: AbstractRobustConnection | None = None
        self.publisher: RabbitMQMessagePublisher | None = None
        self.page_consumer: RabbitMQPageTaskConsumer | None = None
        self.start_consumer: RabbitMQStartCrawlConsumer | None = None

        self.consumer_task: asyncio.Task[None] | None = None
        self.start_consumer_task: asyncio.Task[None] | None = None
        self.dispatcher_task: asyncio.Task[None] | None = None

        self._ready = False

    @property
    def ready(self) -> bool:
        return (
            self._ready
            and self.consumer_task is not None
            and not self.consumer_task.done()
            and self.start_consumer_task is not None
            and not self.start_consumer_task.done()
            and self.dispatcher_task is not None
            and not self.dispatcher_task.done()
        )

    async def start(self) -> None:
        if self._ready:
            raise RuntimeError("Capture runtime has already started")

        try:
            session = boto3.Session(
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key,
            )

            self.dynamodb_client = session.client(
                "dynamodb",
                region_name=self.settings.aws_region,
                endpoint_url=self.settings.dynamodb_endpoint_url,
            )

            self.s3_client = session.client(
                "s3",
                region_name=self.settings.aws_region,
                endpoint_url=self.settings.s3_endpoint_url,
            )

            for table_name in CAPTURE_TABLES:
                await asyncio.to_thread(
                    self.dynamodb_client.describe_table,
                    TableName=table_name,
                )

            self.archive_retrieval = DynamoDBArchiveRetrieval(
                client=self.dynamodb_client,
                s3_client=self.s3_client,
                artifact_bucket=ARCHIVE_ARTIFACTS_BUCKET,
            )

            task_repository = DynamoDBTaskRepository(
                client=self.dynamodb_client,
                lease_duration=self.settings.lease_duration,
            )

            allocator = DynamoDBCaptureAllocator(
                client=self.dynamodb_client,
                slot_count=self.settings.browser_slot_count,
                lease_duration=self.settings.lease_duration,
            )

            auth_contexts = StoredAuthContexts(
                sessions=DynamoDBSessionStore(client=self.dynamodb_client),
                profiles=EncryptedAuthProfileStore(
                    s3_client=self.s3_client,
                    cipher=AuthProfileCipher(self.settings.auth_profile_key),
                ),
            )

            worker = new_worker(
                task_repository=task_repository,
                capture_allocator=allocator,
                executor=BrowserPageExecutor(),
                artifacts=S3ArtifactStore(
                    client=self.s3_client,
                    staging_root=Path(self.settings.artifact_directory),
                ),
                auth_contexts=auth_contexts,
            )

            self.connection = cast(
                AbstractRobustConnection,
                await cast(Any, aio_pika).connect_robust(self.settings.rabbitmq_url),
            )

            self.publisher = RabbitMQMessagePublisher(self.connection)

            await self.publisher.start()

            consumer_ready = asyncio.Event()

            self.page_consumer = RabbitMQPageTaskConsumer(self.connection)

            processor = PageTaskProcessor(consumer=self.page_consumer, worker=worker)

            self.consumer_task = asyncio.create_task(
                processor.run(ready=consumer_ready),
                name="capture-rabbitmq-consumer",
            )

            await asyncio.wait_for(
                consumer_ready.wait(),
                timeout=CONSUMER_START_TIMEOUT_SECONDS,
            )

            start_ready = asyncio.Event()

            self.start_consumer = RabbitMQStartCrawlConsumer(self.connection)

            start_processor = StartCrawlProcessor(
                consumer=self.start_consumer,
                starter=DynamoDBRunStarter(client=self.dynamodb_client),
            )

            self.start_consumer_task = asyncio.create_task(
                start_processor.run(ready=start_ready),
                name="capture-start-crawl-consumer",
            )

            await asyncio.wait_for(
                start_ready.wait(),
                timeout=CONSUMER_START_TIMEOUT_SECONDS,
            )

            dispatcher = OutboxDispatcher(
                outbox=DynamoDBOutbox(client=self.dynamodb_client),
                publisher=self.publisher,
                lease_duration=self.settings.outbox_lease_duration,
                retry_delay=self.settings.outbox_retry_delay,
                poll_interval=self.settings.outbox_poll_interval,
            )

            self.dispatcher_task = asyncio.create_task(
                dispatcher.run(),
                name="capture-outbox-dispatcher",
            )

            self._ready = True
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        self._ready = False

        self.archive_retrieval = None

        if self.page_consumer is not None:
            self.page_consumer.stop()

        if self.start_consumer is not None:
            self.start_consumer.stop()

        if self.dispatcher_task is not None and not self.dispatcher_task.done():
            self.dispatcher_task.cancel()

        tasks = [
            task
            for task in (
                self.consumer_task,
                self.start_consumer_task,
                self.dispatcher_task,
            )
            if task is not None and not task.done()
        ]

        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=SHUTDOWN_TIMEOUT_SECONDS)

            for task in pending:
                task.cancel()

            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        self.page_consumer = None
        self.start_consumer = None
        self.consumer_task = None
        self.start_consumer_task = None
        self.dispatcher_task = None

        try:
            if self.publisher is not None:
                await self.publisher.close()
                self.publisher = None
        finally:
            try:
                if self.connection is not None:
                    await self.connection.close()
                    self.connection = None
            finally:
                try:
                    if self.s3_client is not None:
                        self.s3_client.close()
                        self.s3_client = None
                finally:
                    if self.dynamodb_client is not None:
                        self.dynamodb_client.close()
                        self.dynamodb_client = None
