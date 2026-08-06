"""Offline proof for the Milestone 11 infrastructure boundaries."""

from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.distributed import InMemoryDistributedStore
from backend.app.jobs import InMemoryJobQueue, Job, JobStatus
from backend.app.storage import LocalObjectStorage


def main() -> None:
    store = InMemoryDistributedStore()
    assert store.increment("limit:learner", 60) == 1
    assert store.claim("lock:cleanup", "worker-1", 30)
    queue = InMemoryJobQueue()
    job = queue.submit(Job("cleanup", {"batch": "100"}, "cleanup:2026-08-06"))
    queue.run_next({"cleanup": lambda payload: payload["batch"]})
    assert job.status == JobStatus.SUCCEEDED
    with TemporaryDirectory() as directory:
        storage = LocalObjectStorage(Path(directory), "deterministic-signing-key-32-bytes")
        reference = storage.put("learner/audio.webm", b"audio", "audio/webm")
        assert storage.delete(reference)
    print("deterministic_production_infrastructure_ok")


if __name__ == "__main__":
    main()
