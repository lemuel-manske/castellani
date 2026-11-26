import asyncio

from domain.capture import (
    CompensationDecision,
    InvalidArchiveDecision,
    PublicationDecision,
)
from ports.artifacts import DecisionArtifacts
from ports.capture import ArchivePublicationRepository
from ports.messaging import (
    ArchiveCompensationConsumer,
    ArchiveCompensationMessage,
    ArchivePublicationConsumer,
    ArchivePublicationMessage,
)


class ArchiveDecisionProcessor:
    """Applies Coordinator decisions to durable Capture facts."""

    def __init__(
        self,
        repository: ArchivePublicationRepository,
        artifacts: DecisionArtifacts,
        publication_consumer: ArchivePublicationConsumer,
        compensation_consumer: ArchiveCompensationConsumer,
    ) -> None:
        self.repository = repository
        self.artifacts = artifacts
        self.publication_consumer = publication_consumer
        self.compensation_consumer = compensation_consumer

    async def run(self, ready: asyncio.Event | None = None) -> None:
        publication_ready = asyncio.Event()
        compensation_ready = asyncio.Event()

        tasks = [
            asyncio.create_task(
                self._consume_publications(publication_ready),
                name="capture-publication-decisions",
            ),
            asyncio.create_task(
                self._consume_compensations(compensation_ready),
                name="capture-compensation-decisions",
            ),
        ]

        if ready is not None:

            async def signal_ready() -> None:
                await publication_ready.wait()
                await compensation_ready.wait()
                ready.set()

            tasks.append(asyncio.create_task(signal_ready(), name="capture-decisions-ready"))

        await asyncio.gather(*tasks)

    async def process_publication(self, message: ArchivePublicationMessage) -> None:
        if message.retry_exhausted or message.correlation_id != message.archive_id:
            await message.dead_letter()

            return

        decision = PublicationDecision(
            archive_id=message.archive_id,
            correlation_id=message.correlation_id,
            decision_version=message.decision_version,
            package_digest=message.package_digest,
            occurred_at=message.occurred_at,
        )

        try:
            await self.repository.accept_publication(decision)
        except InvalidArchiveDecision:
            await message.dead_letter()
        except Exception:
            await message.reject()
        else:
            await message.ack()

    async def process_compensation(self, message: ArchiveCompensationMessage) -> None:
        if message.retry_exhausted or message.correlation_id != message.archive_id:
            await message.dead_letter()

            return

        decision = CompensationDecision(
            archive_id=message.archive_id,
            correlation_id=message.correlation_id,
            decision_version=message.decision_version,
            reason_code=message.reason_code,
            occurred_at=message.occurred_at,
        )

        try:
            await self.repository.begin_compensation(decision)
        except InvalidArchiveDecision:
            await message.dead_letter()

            return
        except Exception:
            await message.reject()

            return

        try:
            await self.artifacts.delete_archive_objects(decision.archive_id)
            await self.repository.complete_compensation(decision)
        except InvalidArchiveDecision:
            await message.dead_letter()
        except Exception:
            await message.reject()
        else:
            await message.ack()

    async def _consume_publications(self, ready: asyncio.Event) -> None:
        async for message in self.publication_consumer.messages(ready=ready):
            await self.process_publication(message)

    async def _consume_compensations(self, ready: asyncio.Event) -> None:
        async for message in self.compensation_consumer.messages(ready=ready):
            await self.process_compensation(message)
