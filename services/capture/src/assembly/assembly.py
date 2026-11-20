from collections.abc import Awaitable, Callable
from typing import TypeVar

from application.contracts import (
    ArtifactStore,
    BrowserCapacity,
    DiscoveryPublisher,
    PageExecutor,
    TaskRepository,
)
from application.worker import Worker, WorkerRuntime

Delivery = TypeVar("Delivery")


def new_worker(
    repository: TaskRepository,
    capacity: BrowserCapacity,
    executor: PageExecutor,
    artifacts: ArtifactStore,
    discovery: DiscoveryPublisher,
) -> Worker:
    return Worker(
        repository=repository,
        capacity=capacity,
        executor=executor,
        artifacts=artifacts,
        discovery=discovery,
    )


def new_worker_runtime(
    worker: Worker,
    receive: Callable[[], Awaitable[Delivery | None]],
    acknowledge: Callable[[Delivery], Awaitable[None]],
    reject: Callable[[Delivery], Awaitable[None]],
    delivery_parser: Callable[[Delivery], tuple[str, str]],
) -> WorkerRuntime:
    return WorkerRuntime(
        worker=worker,
        receive=receive,
        acknowledge=acknowledge,
        reject=reject,
        delivery_parser=delivery_parser,
    )
