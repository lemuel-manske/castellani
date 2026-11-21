from application.contracts import ArtifactStore, CaptureExecutor
from application.worker import ConcreteCaptureWorker
from domain import CaptureAllocator, TaskRepository


def new_worker(
    repository: TaskRepository,
    capture_allocator: CaptureAllocator,
    executor: CaptureExecutor,
    artifacts: ArtifactStore,
) -> ConcreteCaptureWorker:
    return ConcreteCaptureWorker(
        repository=repository,
        alloc=capture_allocator,
        executor=executor,
        artifacts=artifacts,
    )
