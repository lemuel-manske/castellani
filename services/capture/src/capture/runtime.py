from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import aio_pika
import boto3
from aio_pika.abc import AbstractRobustConnection

from adapters.artifacts.s3 import S3ArtifactStore, S3AuthProfileStore
from adapters.messaging.rabbitmq.consumer import (
    RabbitMQCompensationDecisionConsumer,
    RabbitMQPageTaskConsumer,
    RabbitMQPublicationDecisionConsumer,
    RabbitMQStartCrawlConsumer,
)
from adapters.messaging.rabbitmq.publisher import RabbitMQMessagePublisher
from adapters.persistence.dynamodb.alloc import DynamoDBCaptureAllocator
from adapters.persistence.dynamodb.archive import DynamoDBArchiveCatalog
from adapters.persistence.dynamodb.finalize import DynamoDBArchiveFinalizationRepository
from adapters.persistence.dynamodb.outbox import DynamoDBOutbox
from adapters.persistence.dynamodb.publication import DynamoDBArchivePublicationRepository
from adapters.persistence.dynamodb.run import DynamoDBRunStarter
from adapters.persistence.dynamodb.session import DynamoDBSessionStore
from adapters.persistence.dynamodb.task import DynamoDBTaskRepository
from application.capture import OutboxDispatcher, StoredAuthContexts
from application.capture.archive_decisions import ArchiveDecisionProcessor
from application.capture.archive_finalization import ArchiveManifestFinalizer
from application.capture.archive_preparation import ArchivePackager
from application.capture.archive_retrieval import ArchiveRetrieval
from application.capture.page_tasks import PageTaskProcessor
from application.capture.start_crawls import StartCrawlProcessor
from ports.login import AuthProfileCipher
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
        self.archive_retrieval: ArchiveRetrieval | None = None

        self.connection: AbstractRobustConnection | None = None
        self.publisher: RabbitMQMessagePublisher | None = None
        self.page_consumer: RabbitMQPageTaskConsumer | None = None
        self.start_consumer: RabbitMQStartCrawlConsumer | None = None
        self.publication_consumer: RabbitMQPublicationDecisionConsumer | None = None
        self.compensation_consumer: RabbitMQCompensationDecisionConsumer | None = None

        self.consumer_task: asyncio.Task[None] | None = None
        self.start_consumer_task: asyncio.Task[None] | None = None
        self.packaging_task: asyncio.Task[None] | None = None
        self.decisions_task: asyncio.Task[None] | None = None
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
            and self.packaging_task is not None
            and not self.packaging_task.done()
            and self.decisions_task is not None
            and not self.decisions_task.done()
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

            artifacts = S3ArtifactStore(
                client=self.s3_client,
                staging_root=Path(self.settings.artifact_directory),
            )

            catalog = DynamoDBArchiveCatalog(client=self.dynamodb_client)

            self.archive_retrieval = ArchiveRetrieval(
                catalog=catalog,
                artifacts=artifacts,
            )

            finalizer = ArchiveManifestFinalizer(
                repository=DynamoDBArchiveFinalizationRepository(client=self.dynamodb_client),
                artifacts=artifacts,
            )

            task_repository = DynamoDBTaskRepository(
                client=self.dynamodb_client,
                lease_duration=self.settings.lease_duration,
                finalize=finalizer,
            )

            allocator = DynamoDBCaptureAllocator(
                client=self.dynamodb_client,
                slot_count=self.settings.browser_slot_count,
                lease_duration=self.settings.lease_duration,
            )

            auth_contexts = StoredAuthContexts(
                sessions=DynamoDBSessionStore(client=self.dynamodb_client),
                profiles=S3AuthProfileStore(
                    s3_client=self.s3_client,
                    cipher=AuthProfileCipher(self.settings.auth_profile_key),
                ),
            )

            worker = new_worker(
                task_repository=task_repository,
                capture_allocator=allocator,
                artifacts=artifacts,
                auth_contexts=auth_contexts,
            )

            self.connection = cast(
                AbstractRobustConnection,
                await cast(Any, aio_pika).connect_robust(self.settings.rabbitmq_url),
            )

            self.publisher = RabbitMQMessagePublisher(self.connection)

            await self.publisher.start()

            publication_repository = DynamoDBArchivePublicationRepository(
                client=self.dynamodb_client,
            )

            self.packaging_task = asyncio.create_task(
                ArchivePackager(
                    repository=publication_repository,
                    artifacts=artifacts,
                    root=self.settings.packages_directory,
                    lease_duration=self.settings.outbox_lease_duration,
                    poll_interval=self.settings.outbox_poll_interval,
                ).run(),
                name="capture-archive-packager",
            )

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

            decisions_ready = asyncio.Event()

            self.publication_consumer = RabbitMQPublicationDecisionConsumer(self.connection)
            self.compensation_consumer = RabbitMQCompensationDecisionConsumer(self.connection)

            decision_processor = ArchiveDecisionProcessor(
                repository=publication_repository,
                artifacts=artifacts,
                publication_consumer=self.publication_consumer,
                compensation_consumer=self.compensation_consumer,
            )

            self.decisions_task = asyncio.create_task(
                decision_processor.run(ready=decisions_ready),
                name="capture-archive-decisions",
            )

            await asyncio.wait_for(
                decisions_ready.wait(),
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

        if self.publication_consumer is not None:
            self.publication_consumer.stop()

        if self.compensation_consumer is not None:
            self.compensation_consumer.stop()

        for task in (
            self.packaging_task,
            self.decisions_task,
            self.dispatcher_task,
        ):
            if task is not None and not task.done():
                task.cancel()

        tasks = [
            task
            for task in (
                self.consumer_task,
                self.start_consumer_task,
                self.packaging_task,
                self.decisions_task,
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
        self.publication_consumer = None
        self.compensation_consumer = None

        self.consumer_task = None
        self.start_consumer_task = None
        self.packaging_task = None
        self.decisions_task = None
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
