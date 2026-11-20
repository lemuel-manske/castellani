from collections.abc import Callable

from application.contracts import PageTaskDelivery
from application.worker import WorkerRuntime


class SuccessfulWorker:
    def __init__(self) -> None:
        self.deliveries: list[tuple[str, str]] = []

    async def execute(self, archive_id: str, url_key: str) -> bool:
        self.deliveries.append((archive_id, url_key))

        return True


class FailingWorker:
    async def execute(self, archive_id: str, url_key: str) -> bool:
        raise RuntimeError("capture state unavailable")


class ReceivedMessage:
    def __init__(self, delivery: PageTaskDelivery) -> None:
        self.delivery = delivery
        self.acknowledged = False
        self.rejected = False
        self.on_settled: Callable[[], None] = lambda: None

    async def acknowledge(self) -> None:
        self.acknowledged = True
        self.on_settled()

    async def reject(self) -> None:
        self.rejected = True
        self.on_settled()


class SingleMessageConsumer:
    def __init__(self, message: ReceivedMessage) -> None:
        self.message = message

    async def receive(self) -> ReceivedMessage:
        return self.message


async def test_runtime_acknowledges_a_processed_delivery() -> None:
    worker = SuccessfulWorker()
    message = ReceivedMessage(PageTaskDelivery("archive-1", "url-1"))
    runtime = WorkerRuntime(worker, SingleMessageConsumer(message))
    message.on_settled = runtime.stop

    await runtime.run()

    assert worker.deliveries == [("archive-1", "url-1")]
    assert message.acknowledged
    assert not message.rejected


async def test_runtime_rejects_a_delivery_when_processing_raises() -> None:
    message = ReceivedMessage(PageTaskDelivery("archive-1", "url-1"))
    runtime = WorkerRuntime(FailingWorker(), SingleMessageConsumer(message))
    message.on_settled = runtime.stop

    await runtime.run()

    assert message.rejected
    assert not message.acknowledged
