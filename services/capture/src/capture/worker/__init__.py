from ports.capture import AuthContextStore, CaptureAllocator, TaskRepository
from ports.worker import ArtifactStore, CaptureArtifact, CaptureRunner, LeaseLostError

from .runner import ConcreteCaptureWorker


def new_worker(
    task_repository: TaskRepository,
    capture_allocator: CaptureAllocator,
    artifacts: ArtifactStore,
    auth_contexts: AuthContextStore,
) -> ConcreteCaptureWorker:
    return ConcreteCaptureWorker(
        task_repository=task_repository,
        capture_allocator=capture_allocator,
        artifacts=artifacts,
        auth_contexts=auth_contexts,
    )


__all__ = [
    "ArtifactStore",
    "CaptureArtifact",
    "CaptureRunner",
    "LeaseLostError",
    "new_worker",
]
