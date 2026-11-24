from domain.capture import CaptureAllocator, TaskRepository

from .api import (
    ArtifactStore,
    CaptureArtifact,
    CaptureExecutor,
    CaptureRunner,
    LeaseLostError,
)
from .runner import ConcreteCaptureWorker


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
    "new_worker",
]
