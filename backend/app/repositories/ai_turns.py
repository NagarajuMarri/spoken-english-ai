from datetime import datetime, timezone

from sqlalchemy import select

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
    ) -> AITurnAttempt:
        attempt = AITurnAttempt(
            conversation_id=conversation_id,
            learner_id=learner_id,
            idempotency_key=idempotency_key,
            learner_text=learner_text,
            status="IN_PROGRESS",
            result_json={},
        )
        self.session.add(attempt)
        self.session.commit()
        return attempt

    def mark_in_progress(self, attempt: AITurnAttempt) -> None:
        attempt.status = "IN_PROGRESS"
        attempt.failure_code = None
        attempt.updated_at = utc_now()
        self.session.commit()

    def mark_review_in_progress(self, attempt: AITurnAttempt) -> None:
        attempt.status = "REVIEW_IN_PROGRESS"
        attempt.failure_code = None
        attempt.updated_at = utc_now()
        self.session.commit()

    def checkpoint_provider_success(
        self,
        attempt: AITurnAttempt,
        response,
        *,
        provider_latency_ms: float,
    ) -> None:
        attempt.status = "PROVIDER_SUCCEEDED"
        attempt.failure_code = None
        attempt.provider_attempts += response.usage.provider_requests
        attempt.result_json = {
            "provider_response": response.model_dump(mode="json"),
            "provider_latency_ms": provider_latency_ms,
        }
        attempt.updated_at = utc_now()
        self.session.commit()

    def mark_provider_failure(self, attempt: AITurnAttempt, error) -> None:
        attempt.status = "FAILED_RETRYABLE" if error.retryable else "FAILED_FINAL"
        attempt.failure_code = error.failure_code
        attempt.provider_attempts += error.provider_requests
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
        attempt.provider_attempts += review_result.usage.provider_requests
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
        attempt.provider_attempts += error.provider_requests
        attempt.updated_at = utc_now()
        self.session.commit()

    def mark_review_failure(self, attempt: AITurnAttempt, error) -> None:
        attempt.status = "REVIEW_FAILED_RETRYABLE" if error.retryable else "REVIEW_FAILED_FINAL"
        attempt.failure_code = error.failure_code
        attempt.provider_attempts += error.provider_requests
        attempt.updated_at = utc_now()

    def mark_completed(self, attempt: AITurnAttempt, result: dict) -> None:
        checkpoint = dict(attempt.result_json)
        checkpoint["api_result"] = result
        attempt.result_json = checkpoint
        attempt.status = "COMPLETED"
        attempt.failure_code = None
        attempt.completed_at = utc_now()
        attempt.updated_at = attempt.completed_at
