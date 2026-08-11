from __future__ import annotations

from typing import Protocol

from backend.app.jobs import Job, RedisJobQueue


PASSWORD_RESET_EMAIL_JOB_KIND = "password_reset_email"


class PasswordResetDispatch(Protocol):
    def dispatch(self, reset_token_id: str, recipient: str, verification_code: str) -> None: ...


class DirectPasswordResetDispatch:
    """Development/test dispatch; production must use the durable Redis boundary."""

    def __init__(self, delivery) -> None:
        self.delivery = delivery

    def dispatch(self, reset_token_id: str, recipient: str, verification_code: str) -> None:
        _ = reset_token_id
        self.delivery.deliver(recipient, verification_code)


class RedisPasswordResetDispatch:
    """Enqueue reset delivery without placing the recipient in Redis."""

    def __init__(
        self,
        queue: RedisJobQueue,
        *,
        maximum_attempts: int,
        idempotency_ttl_seconds: int,
    ) -> None:
        self.queue = queue
        self.maximum_attempts = maximum_attempts
        self.idempotency_ttl_seconds = idempotency_ttl_seconds

    def dispatch(self, reset_token_id: str, recipient: str, verification_code: str) -> None:
        _ = recipient
        job = Job(
            kind=PASSWORD_RESET_EMAIL_JOB_KIND,
            payload={
                "password_reset_token_id": reset_token_id,
                "verification_code": verification_code,
            },
            idempotency_key=f"password-reset-email:{reset_token_id}",
            max_attempts=self.maximum_attempts,
        )
        self.queue.submit(
            job,
            idempotency_ttl_seconds=self.idempotency_ttl_seconds,
        )


def build_password_reset_dispatch(settings, delivery, queue: RedisJobQueue | None):
    if settings.environment == "production":
        if queue is None:
            raise RuntimeError("Production password-reset dispatch requires Redis.")
        return RedisPasswordResetDispatch(
            queue,
            maximum_attempts=settings.password_reset_job_max_attempts,
            idempotency_ttl_seconds=settings.password_reset_job_idempotency_ttl_seconds,
        )
    return DirectPasswordResetDispatch(delivery)
