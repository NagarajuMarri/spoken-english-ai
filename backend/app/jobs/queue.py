from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
from typing import Callable
from uuid import uuid4


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
        self.dead_letter_key = f"{namespace}:jobs:dead-letter"
        self.idempotency_prefix = f"{namespace}:job:idempotency:"

    def submit(self, job: Job, idempotency_ttl_seconds: int = 86_400) -> Job:
        claimed = self.client.set(
            self.idempotency_prefix + job.idempotency_key,
            job.job_id,
            nx=True,
            ex=idempotency_ttl_seconds,
        )
        if claimed:
            self.client.lpush(self.queue_key, self._encode(job))
        return job

    def take(self, timeout_seconds: int = 5) -> Job | None:
        item = self.client.brpop(self.queue_key, timeout=timeout_seconds)
        return self._decode(item[1]) if item else None

    def complete(self, job: Job) -> None:
        job.status = JobStatus.SUCCEEDED

    def fail(self, job: Job) -> None:
        job.attempts += 1
        if job.attempts < job.max_attempts:
            job.status = JobStatus.RETRYING
            self.client.lpush(self.queue_key, self._encode(job))
        else:
            job.status = JobStatus.DEAD_LETTER
            self.client.lpush(self.dead_letter_key, self._encode(job))

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
