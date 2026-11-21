from domain import TaskRepository
from domain.alloc import CaptureAllocator

from .api import (
    ArtifactStore,
    CaptureArtifact,
    CaptureExecutor,
    CaptureRunner,
    LeaseLostError,
)
from .artifacts import LocalArtifactStore
from .worker import ConcreteCaptureWorker


def new_worker(
    task_repository: TaskRepository,
    capture_allocator: CaptureAllocator,
    executor: CaptureExecutor,
    artifacts: ArtifactStore,
) -> ConcreteCaptureWorker:
    return ConcreteCaptureWorker(
        task_repository=task_repository,
        capture_allocator=capture_allocator,
        executor=executor,
        artifacts=artifacts,
    )


__all__ = [
    "ArtifactStore",
    "CaptureArtifact",
    "CaptureExecutor",
    "CaptureRunner",
    "LeaseLostError",
    "LocalArtifactStore",
    "new_worker",
]
