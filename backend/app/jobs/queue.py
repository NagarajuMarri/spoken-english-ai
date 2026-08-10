from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
from typing import Callable
from uuid import uuid4


_IDEMPOTENT_SUBMIT_SCRIPT = """
local claimed = redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[3])
if claimed then
  redis.call('LPUSH', KEYS[2], ARGV[2])
  return 1
end
return 0
"""


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    RETRYING = "RETRYING"
    DEAD_LETTER = "DEAD_LETTER"


@dataclass
class Job:
    kind: str
    payload: dict[str, str]
    idempotency_key: str
    max_attempts: int = 3
    job_id: str = field(default_factory=lambda: uuid4().hex)
    status: JobStatus = JobStatus.QUEUED
    attempts: int = 0
    audit: list[dict[str, str]] = field(default_factory=list)
    receipt: bytes | str | None = field(default=None, repr=False, compare=False)


class InMemoryJobQueue:
    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self._keys: set[str] = set()
        self.shutting_down = False

    def submit(self, job: Job) -> Job:
        if job.idempotency_key in self._keys:
            return next(item for item in self.jobs if item.idempotency_key == job.idempotency_key)
        self._keys.add(job.idempotency_key)
        self.jobs.append(job)
        self._record(job, "submitted")
        return job

    def run_next(self, handlers: dict[str, Callable[[dict[str, str]], None]]) -> Job | None:
        if self.shutting_down:
            return None
        job = next((item for item in self.jobs if item.status in {JobStatus.QUEUED, JobStatus.RETRYING}), None)
        if not job:
            return None
        job.status = JobStatus.RUNNING
        job.attempts += 1
        self._record(job, "started")
        try:
            handlers[job.kind](job.payload)
            job.status = JobStatus.SUCCEEDED
            self._record(job, "succeeded")
        except Exception:
            job.status = JobStatus.RETRYING if job.attempts < job.max_attempts else JobStatus.DEAD_LETTER
            self._record(job, "retrying" if job.status == JobStatus.RETRYING else "dead_letter")
        return job

    def shutdown(self) -> None:
        self.shutting_down = True

    @staticmethod
    def _record(job: Job, event: str) -> None:
        job.audit.append({"event": event, "at": datetime.now(timezone.utc).isoformat()})


class RedisJobQueue:
    """Durable Redis queue with idempotent submission and bounded retries."""

    def __init__(self, client, namespace: str = "spoken-english") -> None:
        self.client = client
        self.queue_key = f"{namespace}:jobs"
        self.processing_key = f"{namespace}:jobs:processing"
        self.dead_letter_key = f"{namespace}:jobs:dead-letter"
        self.idempotency_prefix = f"{namespace}:job:idempotency:"

    def submit(self, job: Job, idempotency_ttl_seconds: int = 86_400) -> Job:
        idempotency_key = self.idempotency_prefix + job.idempotency_key
        self.client.eval(
            _IDEMPOTENT_SUBMIT_SCRIPT,
            2,
            idempotency_key,
            self.queue_key,
            job.job_id,
            self._encode(job),
            idempotency_ttl_seconds,
        )
        return job

    def take(self, timeout_seconds: int = 5) -> Job | None:
        payload = self.client.brpoplpush(
            self.queue_key,
            self.processing_key,
            timeout=timeout_seconds,
        )
        if payload is None:
            return None
        job = self._decode(payload)
        job.receipt = payload
        job.status = JobStatus.RUNNING
        return job

    def complete(self, job: Job) -> None:
        job.status = JobStatus.SUCCEEDED
        self._acknowledge(job)

    def fail(
        self,
        job: Job,
        *,
        dead_letter_payload: dict[str, str] | None = None,
    ) -> None:
        job.attempts += 1
        if job.attempts < job.max_attempts:
            job.status = JobStatus.RETRYING
            self._transfer(job, self.queue_key)
        else:
            job.status = JobStatus.DEAD_LETTER
            if dead_letter_payload is not None:
                job.payload = dict(dead_letter_payload)
                job.idempotency_key = "redacted"
            self._transfer(job, self.dead_letter_key)

    def recover_inflight(self) -> int:
        """Return work left in-flight by a stopped single-replica worker."""

        recovered = 0
        while self.client.rpoplpush(self.processing_key, self.queue_key) is not None:
            recovered += 1
        return recovered

    def _acknowledge(self, job: Job) -> None:
        if job.receipt is None:
            return
        self.client.lrem(self.processing_key, 1, job.receipt)
        job.receipt = None

    def _transfer(self, job: Job, destination: str) -> None:
        encoded = self._encode(job)
        if job.receipt is None:
            self.client.lpush(destination, encoded)
            return
        pipeline = self.client.pipeline(transaction=True)
        pipeline.lrem(self.processing_key, 1, job.receipt)
        pipeline.lpush(destination, encoded)
        pipeline.execute()
        job.receipt = None

    @staticmethod
    def _encode(job: Job) -> str:
        return json.dumps({
            "kind": job.kind,
            "payload": job.payload,
            "idempotency_key": job.idempotency_key,
            "max_attempts": job.max_attempts,
            "job_id": job.job_id,
            "status": job.status.value,
            "attempts": job.attempts,
            "audit": job.audit,
        }, separators=(",", ":"))

    @staticmethod
    def _decode(payload: bytes | str) -> Job:
        data = json.loads(payload)
        return Job(
            kind=data["kind"],
            payload=data["payload"],
            idempotency_key=data["idempotency_key"],
            max_attempts=data["max_attempts"],
            job_id=data["job_id"],
            status=JobStatus(data["status"]),
            attempts=data["attempts"],
            audit=data["audit"],
        )
