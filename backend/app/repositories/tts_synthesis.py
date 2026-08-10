from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
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
               input_characters: int, commit: bool = True) -> TTSSynthesisAttempt:
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
            provider_requests=1,
            usage_classification="CHARACTERS_AND_BYTES_PROVIDER_TOKEN_USAGE_UNAVAILABLE",
        )
        self.session.add(attempt)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        self.session.refresh(attempt)
        return attempt

    def claim_retry(
        self,
        attempt: TTSSynthesisAttempt,
        *,
        maximum_provider_requests: int,
        commit: bool = True,
    ) -> bool:
        claimed = cast(CursorResult[Any], self.session.execute(
            update(TTSSynthesisAttempt)
            .where(
                TTSSynthesisAttempt.id == attempt.id,
                TTSSynthesisAttempt.status == "RETRYABLE_FAILURE",
                TTSSynthesisAttempt.provider_requests < maximum_provider_requests,
            )
            .values(
                status="IN_PROGRESS",
                failure_code=None,
                provider_requests=TTSSynthesisAttempt.provider_requests + 1,
                updated_at=datetime.now(timezone.utc),
            )
            .execution_options(synchronize_session=False)
        )).rowcount == 1
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        if claimed:
            self.session.refresh(attempt)
        return claimed

    def succeed(self, attempt: TTSSynthesisAttempt, result, *, commit: bool = True) -> None:
        attempt.status = "SUCCEEDED"
        attempt.failure_code = None
        attempt.content_type = result.content_type
        attempt.audio_bytes = result.audio_bytes
        attempt.audio_size_bytes = len(result.audio_bytes)
        attempt.provider_requests = max(
            0,
            attempt.provider_requests + result.provider_requests - 1,
        )
        attempt.generation_latency_ms = result.generation_latency_ms
        attempt.completed_at = datetime.now(timezone.utc)
        if commit:
            self.session.commit()
        else:
            self.session.flush()

    def fail(
        self,
        attempt: TTSSynthesisAttempt,
        failure_code: str,
        provider_requests: int = 1,
        *,
        commit: bool = True,
    ) -> None:
        attempt.status = "RETRYABLE_FAILURE"
        attempt.failure_code = failure_code
        attempt.provider_requests = max(0, attempt.provider_requests + provider_requests - 1)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
