from application.contracts import ArtifactStore, PageExecutor
from application.worker import Worker
from domain import BrowserCapacity, TaskRepository


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
