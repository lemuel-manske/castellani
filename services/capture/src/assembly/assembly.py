from application.contracts import (
    ArtifactStore,
    BrowserCapacity,
    PageExecutor,
    TaskRepository,
)
from application.worker import Worker


def new_worker(
    repository: TaskRepository,
    capacity: BrowserCapacity,
    executor: PageExecutor,
    artifacts: ArtifactStore,
) -> Worker:
    return Worker(
        repository=repository,
        capacity=capacity,
        executor=executor,
        artifacts=artifacts,
    )
