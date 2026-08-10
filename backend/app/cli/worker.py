"""Explicit Redis worker entry point; importing the application never starts it."""

import signal
import time

from redis import Redis

from backend.app.core.config import get_settings
from backend.app.db.session import build_engine, build_session_factory
from backend.app.jobs import Job, JobStatus, RedisJobQueue
from backend.app.providers.password_reset import build_password_reset_delivery
from backend.app.providers.password_reset.dispatch import PASSWORD_RESET_EMAIL_JOB_KIND
from backend.app.providers.password_reset.jobs import (
    PasswordResetEmailJobHandler,
    PasswordResetJobPermanentError,
)


_SAFE_PASSWORD_RESET_DEAD_LETTER = {
    "outcome": "terminal_failure",
    "sensitive_payload": "redacted",
}


def process_job(
    queue: RedisJobQueue,
    job: Job,
    password_reset_handler: PasswordResetEmailJobHandler,
) -> None:
    if job.kind == "healthcheck":
        queue.complete(job)
        return
    if job.kind != PASSWORD_RESET_EMAIL_JOB_KIND:
        job.max_attempts = min(job.max_attempts, job.attempts + 1)
        queue.fail(job, dead_letter_payload={
            "outcome": "unsupported_job_kind",
            "sensitive_payload": "redacted",
        })
        return
    try:
        password_reset_handler.deliver(job.payload)
    except PasswordResetJobPermanentError:
        password_reset_handler.terminal_failure(job.payload)
        job.max_attempts = min(job.max_attempts, job.attempts + 1)
        queue.fail(job, dead_letter_payload=_SAFE_PASSWORD_RESET_DEAD_LETTER)
    except Exception:
        terminal = job.attempts + 1 >= job.max_attempts
        if terminal:
            password_reset_handler.terminal_failure(job.payload)
            queue.fail(job, dead_letter_payload=_SAFE_PASSWORD_RESET_DEAD_LETTER)
        else:
            queue.fail(job)
    else:
        queue.complete(job)


def main() -> None:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("SPOKEN_ENGLISH_REDIS_URL is required for the worker")
    if not settings.worker_enabled:
        raise RuntimeError("SPOKEN_ENGLISH_WORKER_ENABLED must be true for the worker")
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=5)
    queue = RedisJobQueue(client)
    queue.recover_inflight()
    engine = build_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        pool_timeout_seconds=settings.database_pool_timeout_seconds,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    password_reset_handler = PasswordResetEmailJobHandler(
        build_session_factory(engine),
        build_password_reset_delivery(settings),
        public_frontend_url=settings.public_frontend_url,
    )
    shutting_down = False

    def stop(*_args) -> None:
        nonlocal shutting_down
        shutting_down = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not shutting_down:
            client.set(
                settings.worker_heartbeat_key,
                str(time.time()),
                ex=settings.worker_heartbeat_ttl_seconds,
            )
            job = queue.take(timeout_seconds=5)
            if job is None:
                continue
            process_job(queue, job, password_reset_handler)
            if job.status == JobStatus.RETRYING and not shutting_down:
                time.sleep(settings.password_reset_job_retry_delay_seconds)
    finally:
        client.delete(settings.worker_heartbeat_key)
        client.close()
        engine.dispose()


if __name__ == "__main__":
    main()
