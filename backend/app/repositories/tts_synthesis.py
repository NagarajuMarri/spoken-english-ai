from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import TTSSynthesisAttempt


class TTSSynthesisRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, ai_turn_attempt_id: str) -> TTSSynthesisAttempt | None:
        return self.session.scalar(select(TTSSynthesisAttempt).where(
            TTSSynthesisAttempt.ai_turn_attempt_id == ai_turn_attempt_id
        ))

    def create(self, *, ai_turn_attempt_id: str, learner_id: str, tutor_id: str,
               provider: str, model: str, voice: str, spoken_text_hash: str,
               input_characters: int) -> TTSSynthesisAttempt:
        attempt = TTSSynthesisAttempt(
            ai_turn_attempt_id=ai_turn_attempt_id,
            learner_id=learner_id,
            tutor_id=tutor_id,
            provider=provider,
            model_used=model,
            voice_used=voice,
            spoken_text_hash=spoken_text_hash,
            status="IN_PROGRESS",
            input_characters=input_characters,
            usage_classification="CHARACTERS_AND_BYTES_PROVIDER_TOKEN_USAGE_UNAVAILABLE",
        )
        self.session.add(attempt)
        self.session.commit()
        self.session.refresh(attempt)
        return attempt

    def retry(self, attempt: TTSSynthesisAttempt) -> None:
        attempt.status = "IN_PROGRESS"
        attempt.failure_code = None
        self.session.commit()

    def succeed(self, attempt: TTSSynthesisAttempt, result) -> None:
        attempt.status = "SUCCEEDED"
        attempt.failure_code = None
        attempt.content_type = result.content_type
        attempt.audio_bytes = result.audio_bytes
        attempt.audio_size_bytes = len(result.audio_bytes)
        attempt.provider_requests += result.provider_requests
        attempt.generation_latency_ms = result.generation_latency_ms
        attempt.completed_at = datetime.now(timezone.utc)
        self.session.commit()

    def fail(self, attempt: TTSSynthesisAttempt, failure_code: str, provider_requests: int = 1) -> None:
        attempt.status = "RETRYABLE_FAILURE"
        attempt.failure_code = failure_code
        attempt.provider_requests += provider_requests
        self.session.commit()
