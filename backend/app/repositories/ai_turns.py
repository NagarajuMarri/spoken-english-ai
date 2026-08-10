from datetime import datetime, timezone

from sqlalchemy import select, update

from backend.app.models import AITurnAttempt


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AITurnAttemptRepository:
    def __init__(self, session) -> None:
        self.session = session

    def get(self, conversation_id: str, idempotency_key: str) -> AITurnAttempt | None:
        return self.session.scalar(select(AITurnAttempt).where(
            AITurnAttempt.conversation_id == conversation_id,
            AITurnAttempt.idempotency_key == idempotency_key,
        ))

    def latest_completed(self, conversation_id: str) -> AITurnAttempt | None:
        return self.session.scalar(
            select(AITurnAttempt).where(
                AITurnAttempt.conversation_id == conversation_id,
                AITurnAttempt.status == "COMPLETED",
            ).order_by(AITurnAttempt.completed_at.desc(), AITurnAttempt.created_at.desc()).limit(1)
        )

    def create(
        self,
        *,
        conversation_id: str,
        learner_id: str,
        idempotency_key: str,
        learner_text: str,
        commit: bool = True,
    ) -> AITurnAttempt:
        attempt = AITurnAttempt(
            conversation_id=conversation_id,
            learner_id=learner_id,
            idempotency_key=idempotency_key,
            learner_text=learner_text,
            status="IN_PROGRESS",
            provider_attempts=1,
            result_json={},
        )
        self.session.add(attempt)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return attempt

    def claim_provider_retry(
        self,
        attempt: AITurnAttempt,
        *,
        maximum_provider_requests: int,
        commit: bool = True,
    ) -> bool:
        claimed = self.session.execute(
            update(AITurnAttempt)
            .where(
                AITurnAttempt.id == attempt.id,
                AITurnAttempt.status == "FAILED_RETRYABLE",
                AITurnAttempt.provider_attempts < maximum_provider_requests,
            )
            .values(
                status="IN_PROGRESS",
                failure_code=None,
                provider_attempts=AITurnAttempt.provider_attempts + 1,
                updated_at=utc_now(),
            )
            .execution_options(synchronize_session=False)
        ).rowcount == 1
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        if claimed:
            self.session.refresh(attempt)
        return claimed

    def claim_review(self, attempt: AITurnAttempt, *, commit: bool = True) -> bool:
        claimed = self.session.execute(
            update(AITurnAttempt)
            .where(
                AITurnAttempt.id == attempt.id,
                AITurnAttempt.status.in_(("PROVIDER_SUCCEEDED", "REVIEW_FAILED_RETRYABLE")),
            )
            .values(
                status="REVIEW_IN_PROGRESS",
                failure_code=None,
                provider_attempts=AITurnAttempt.provider_attempts + 1,
                updated_at=utc_now(),
            )
            .execution_options(synchronize_session=False)
        ).rowcount == 1
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        if claimed:
            self.session.refresh(attempt)
        return claimed

    def checkpoint_provider_success(
        self,
        attempt: AITurnAttempt,
        response,
        *,
        provider_latency_ms: float,
    ) -> None:
        attempt.status = "PROVIDER_SUCCEEDED"
        attempt.failure_code = None
        attempt.provider_attempts = max(
            0,
            attempt.provider_attempts + response.usage.provider_requests - 1,
        )
        attempt.result_json = {
            "provider_response": response.model_dump(mode="json"),
            "provider_latency_ms": provider_latency_ms,
        }
        attempt.updated_at = utc_now()
        self.session.commit()

    def mark_provider_failure(
        self,
        attempt: AITurnAttempt,
        error,
        *,
        maximum_provider_requests: int,
    ) -> None:
        attempt.failure_code = error.failure_code
        attempt.provider_attempts = max(
            0,
            attempt.provider_attempts + error.provider_requests - 1,
        )
        attempt.status = (
            "FAILED_RETRYABLE"
            if error.retryable and attempt.provider_attempts < maximum_provider_requests
            else "FAILED_FINAL"
        )
        if attempt.status == "FAILED_FINAL" and error.retryable:
            attempt.failure_code = "provider_retry_limit_reached"
        attempt.updated_at = utc_now()

    def checkpoint_review_success(
        self,
        attempt: AITurnAttempt,
        reviewed_response,
        review_result,
        *,
        review_latency_ms: float,
    ) -> None:
        checkpoint = dict(attempt.result_json)
        checkpoint["reviewed_response"] = reviewed_response.model_dump(mode="json")
        checkpoint["language_review"] = review_result.model_dump(mode="json")
        checkpoint["review_latency_ms"] = review_latency_ms
        attempt.result_json = checkpoint
        attempt.status = "REVIEW_SUCCEEDED"
        attempt.failure_code = None
        attempt.provider_attempts = max(
            0,
            attempt.provider_attempts + review_result.usage.provider_requests - 1,
        )
        attempt.updated_at = utc_now()
        self.session.commit()

    def checkpoint_review_degraded(
        self, attempt, canonical_response, review_result, error, *, review_latency_ms: float,
    ) -> None:
        checkpoint = dict(attempt.result_json)
        checkpoint["reviewed_response"] = canonical_response.model_dump(mode="json")
        checkpoint["language_review"] = review_result.model_dump(mode="json")
        checkpoint["language_review_failure"] = {
            "failure_code": error.failure_code,
            "schema_path": error.schema_path,
            "provider_requests": error.provider_requests,
        }
        checkpoint["review_latency_ms"] = review_latency_ms
        attempt.result_json = checkpoint
        attempt.status = "REVIEW_SUCCEEDED"
        attempt.failure_code = None
        attempt.provider_attempts = max(
            0,
            attempt.provider_attempts + error.provider_requests - 1,
        )
        attempt.updated_at = utc_now()
        self.session.commit()

    def mark_review_failure(self, attempt: AITurnAttempt, error) -> None:
        attempt.status = "REVIEW_FAILED_RETRYABLE" if error.retryable else "REVIEW_FAILED_FINAL"
        attempt.failure_code = error.failure_code
        attempt.provider_attempts = max(
            0,
            attempt.provider_attempts + error.provider_requests - 1,
        )
        attempt.updated_at = utc_now()

    def mark_completed(self, attempt: AITurnAttempt, result: dict) -> None:
        checkpoint = dict(attempt.result_json)
        checkpoint["api_result"] = result
        attempt.result_json = checkpoint
        attempt.status = "COMPLETED"
        attempt.failure_code = None
        attempt.completed_at = utc_now()
        attempt.updated_at = attempt.completed_at
