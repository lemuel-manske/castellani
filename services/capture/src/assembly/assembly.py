from application.contracts import (
    ArtifactStore,
    BrowserCapacity,
    DiscoveryPublisher,
    PageExecutor,
    PageTaskConsumer,
    TaskRepository,
)
from application.worker import Worker, WorkerRuntime


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
    consumer: PageTaskConsumer,
) -> WorkerRuntime:
    return WorkerRuntime(
        worker=worker,
        consumer=consumer,
    )
