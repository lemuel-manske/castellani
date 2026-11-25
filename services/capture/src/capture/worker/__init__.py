from domain.capture import AuthContextStore, CaptureAllocator, TaskRepository

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
    auth_contexts: AuthContextStore,
) -> ConcreteCaptureWorker:
    return ConcreteCaptureWorker(
        task_repository=task_repository,
        capture_allocator=capture_allocator,
        executor=executor,
        artifacts=artifacts,
        auth_contexts=auth_contexts,
    )


__all__ = [
    "ArtifactStore",
    "CaptureArtifact",
    "CaptureExecutor",
    "CaptureRunner",
    "LeaseLostError",
    "new_worker",
]
