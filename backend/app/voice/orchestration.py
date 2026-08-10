from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from backend.app.ai.models import AIConversationRequest
from backend.app.ai.service import AIConversationService
from backend.app.commercial.runtime import RuntimeEntitlementService
from backend.app.conversation_memory.models import MemorySignalInput
from backend.app.conversation_memory.service import ConversationMemoryService
from backend.app.core.errors import AppError
from backend.app.models import (
    AudioAsset,
    ConsentRecord,
    ProviderCallEvent,
    SecurityAuditEvent,
    VoiceProcessingAttempt,
    VoiceSession,
    VoiceTurn,
)
from backend.app.providers.pronunciation.contracts import PronunciationRequest
from backend.app.providers.stt.contracts import SpeechToTextRequest
from backend.app.providers.tts.contracts import TextToSpeechRequest
from backend.app.usage.service import ProviderCallLeaseLost, UsageService
from backend.app.usage.limits import UsageLimits
from backend.app.voice.models import VoiceTutorResult
from fastapi import status


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _provider_request_count(value) -> int:
    try:
        return max(1, int(getattr(value, "provider_requests", 1)))
    except (TypeError, ValueError):
        return 1


class VoiceTutorOrchestrationService:
    """STT and AI are fatal; pronunciation and TTS degrade independently."""

    def __init__(self, session, *, stt, ai, pronunciation, tts, metrics=None, commercial_config=None):
        self.session = session
        self.stt = stt
        self.ai = AIConversationService(ai)
        self.pronunciation = pronunciation
        self.tts = tts
        self.metrics = metrics
        self.commercial_config = commercial_config

    def _audit(self, event_type, learner_id, outcome="SUCCEEDED", reason=None):
        self.session.add(SecurityAuditEvent(
            event_type=event_type, learner_id=learner_id, outcome=outcome,
            reason_code=reason, metadata_json={},
        ))

    def process(
        self,
        *,
        session_id,
        turn_id,
        learner,
        user,
        idempotency_key,
        correlation_id,
        request_id=None,
        generate_audio=True,
    ):
        turn = self.session.get(VoiceTurn, turn_id)
        if turn is None or turn.voice_session_id != session_id:
            raise AppError(status.HTTP_404_NOT_FOUND, "voice_turn_not_found", "Voice turn not found.")
        voice_session = self.session.get(VoiceSession, turn.voice_session_id)
        if voice_session is None or voice_session.learner_id != learner.id:
            raise AppError(status.HTTP_404_NOT_FOUND, "resource_not_found", "Resource not found.")
        existing = self.session.scalar(select(VoiceProcessingAttempt).where(
            VoiceProcessingAttempt.voice_turn_id == turn_id,
            VoiceProcessingAttempt.idempotency_key == idempotency_key,
            VoiceProcessingAttempt.learner_id == learner.id,
        ))
        if existing and existing.status in {"SUCCEEDED", "PARTIALLY_SUCCEEDED"}:
            return VoiceTutorResult.model_validate(existing.result_json)
        if existing and existing.status == "PROCESSING":
            latest_call = self.session.scalar(
                select(ProviderCallEvent).where(
                    ProviderCallEvent.attempt_reference == existing.id,
                    ProviderCallEvent.operation_kind == "voice_pipeline",
                ).order_by(ProviderCallEvent.occurred_at.desc()).limit(1)
            )
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
            lease_time = existing.created_at
            if latest_call is not None:
                lease_time = latest_call.completed_at or latest_call.occurred_at
            if _as_utc(lease_time) > cutoff:
                raise AppError(status.HTTP_409_CONFLICT, "voice_turn_in_progress", "Voice processing is already in progress.")
            if latest_call is not None and latest_call.outcome == "RESERVED":
                fenced = self.session.execute(
                    update(ProviderCallEvent)
                    .where(
                        ProviderCallEvent.id == latest_call.id,
                        ProviderCallEvent.outcome == "RESERVED",
                    )
                    .values(
                        outcome="FAILURE",
                        failed=True,
                        completed_at=datetime.now(timezone.utc),
                    )
                    .execution_options(synchronize_session=False)
                ).rowcount == 1
                if not fenced:
                    self.session.rollback()
                    raise AppError(
                        status.HTTP_409_CONFLICT,
                        "voice_turn_in_progress",
                        "Voice processing is already in progress.",
                    )
            recovered = self.session.execute(
                update(VoiceProcessingAttempt)
                .where(
                    VoiceProcessingAttempt.id == existing.id,
                    VoiceProcessingAttempt.learner_id == learner.id,
                    VoiceProcessingAttempt.status == "PROCESSING",
                )
                .values(
                    status="RETRYABLE_FAILURE",
                    failure_code="provider_lease_expired",
                )
                .execution_options(synchronize_session=False)
            ).rowcount == 1
            if not recovered:
                self.session.rollback()
                self.session.refresh(existing)
                if existing.status in {"SUCCEEDED", "PARTIALLY_SUCCEEDED"}:
                    return VoiceTutorResult.model_validate(existing.result_json)
                raise AppError(
                    status.HTTP_409_CONFLICT,
                    "voice_turn_in_progress",
                    "Voice processing is already in progress.",
                )
            self.session.commit()
            self.session.refresh(existing)
        consent = self.session.scalar(select(ConsentRecord).where(
            ConsentRecord.learner_id == learner.id
        ).order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc()).limit(1))
        if not consent or not consent.voice_processing_consent or consent.consent_withdrawn_at:
            self._audit("VOICE_PROCESSING_CONSENT_BLOCKED", learner.id, "BLOCKED", "consent_required")
            self.session.commit()
            if self.metrics: self.metrics.increment("ai_consent_blocks")
            raise AppError(status.HTTP_403_FORBIDDEN, "voice_consent_required", "Active voice processing consent is required.")
        asset = self.session.get(AudioAsset, turn.audio_asset_id)
        if asset is None or asset.status in {"DELETED", "PENDING_DELETION"}:
            raise AppError(status.HTTP_409_CONFLICT, "audio_unavailable", "Audio is unavailable.")

        usage = UsageService(self.session)
        if self.commercial_config is not None:
            RuntimeEntitlementService(
                self.session,
                self.commercial_config,
            ).enforce_ai_request(learner.id, new_request=existing is None)
            if existing is not None:
                self.session.refresh(existing)
                if existing.status in {"SUCCEEDED", "PARTIALLY_SUCCEEDED"}:
                    return VoiceTutorResult.model_validate(existing.result_json)
                if existing.status == "PROCESSING":
                    raise AppError(
                        status.HTTP_409_CONFLICT,
                        "voice_turn_in_progress",
                        "Voice processing is already in progress.",
                    )
        maximum_provider_requests = UsageLimits().maximum_provider_retries + 1
        if existing is not None:
            previous_attempts = self.session.scalar(
                select(func.count()).select_from(ProviderCallEvent).where(
                    ProviderCallEvent.attempt_reference == existing.id,
                    ProviderCallEvent.operation_kind == "voice_pipeline",
                )
            ) or 0
            if existing.status == "FAILED_FINAL" or previous_attempts >= maximum_provider_requests:
                existing.status = "FAILED_FINAL"
                existing.failure_code = "provider_retry_limit_reached"
                self.session.commit()
                raise AppError(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "voice_retry_limit_reached",
                    "Voice processing could not recover after the allowed retries.",
                )
        usage.enforce(learner.id, user.id, voice_session.id)
        try:
            if existing is not None:
                claimed = self.session.execute(
                    update(VoiceProcessingAttempt)
                    .where(
                        VoiceProcessingAttempt.id == existing.id,
                        VoiceProcessingAttempt.learner_id == learner.id,
                        VoiceProcessingAttempt.status == "RETRYABLE_FAILURE",
                    )
                    .values(status="PROCESSING", failure_code=None)
                    .execution_options(synchronize_session=False)
                ).rowcount == 1
                if not claimed:
                    self.session.rollback()
                    self.session.refresh(existing)
                    if existing.status in {"SUCCEEDED", "PARTIALLY_SUCCEEDED"}:
                        return VoiceTutorResult.model_validate(existing.result_json)
                    raise AppError(
                        status.HTTP_409_CONFLICT,
                        "voice_turn_in_progress",
                        "Voice processing is already in progress.",
                    )
                attempt = existing
                self.session.flush()
                self.session.refresh(attempt)
            else:
                attempt = VoiceProcessingAttempt(
                    voice_turn_id=turn.id,
                    learner_id=learner.id,
                    idempotency_key=idempotency_key,
                    status="PROCESSING",
                )
                self.session.add(attempt)
                self.session.flush()
            provider_call = usage.reserve_provider_call(
                learner_id=learner.id,
                user_id=user.id,
                operation_kind="voice_pipeline",
                attempt_reference=attempt.id,
            )
            attempt_id = str(attempt.id)
            provider_call_id = provider_call.id
            self._audit("VOICE_PROCESSING_STARTED", learner.id)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError(
                status.HTTP_409_CONFLICT,
                "voice_turn_in_progress",
                "Voice processing is already in progress.",
            ) from exc

        provider_requests = 0
        try:
            stt_result = self.stt.transcribe(SpeechToTextRequest(
                audio_asset_reference=asset.storage_key, content_type=asset.media_type,
                learner_id=learner.id, voice_session_id=voice_session.id,
                voice_turn_id=turn.id, correlation_id=correlation_id,
                duration_seconds=1,
            ))
            provider_requests += _provider_request_count(stt_result)
            ai_result = self.ai.generate(AIConversationRequest(
                learner_id=learner.id, conversation_id=voice_session.id,
                learner_level=learner.proficiency_level, preferred_language=learner.native_language,
                scenario=voice_session.scenario_id, topic=voice_session.scenario_id,
                conversation_history=[], current_learner_message=stt_result.transcript,
                correlation_id=correlation_id,
            ))
            provider_requests += _provider_request_count(ai_result.usage)
        except Exception as exc:
            self.session.rollback()
            attempt = self.session.get(VoiceProcessingAttempt, attempt_id)
            provider_requests += _provider_request_count(exc)
            try:
                usage.reconcile_provider_call(
                    provider_call_id,
                    request_count=provider_requests,
                    outcome="FAILURE",
                    failed=True,
                )
            except ProviderCallLeaseLost as lease_exc:
                self.session.rollback()
                raise AppError(
                    status.HTTP_409_CONFLICT,
                    "provider_result_superseded",
                    "This provider result arrived after its processing lease expired. Retry safely.",
                    retryable=True,
                ) from lease_exc
            attempt.status = "RETRYABLE_FAILURE"
            attempt.failure_code = "provider_unavailable"
            self._audit("PROVIDER_FAILED", learner.id, "FAILED", "provider_unavailable")
            attempts = self.session.scalar(
                select(func.count()).select_from(ProviderCallEvent).where(
                    ProviderCallEvent.attempt_reference == attempt.id,
                    ProviderCallEvent.operation_kind == "voice_pipeline",
                )
            ) or 0
            if attempts >= maximum_provider_requests:
                attempt.status = "FAILED_FINAL"
                attempt.failure_code = "provider_retry_limit_reached"
            self.session.commit()
            if self.metrics: self.metrics.increment("voice_turn_failures")
            if attempt.status == "FAILED_FINAL":
                raise AppError(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "voice_retry_limit_reached",
                    "Voice processing could not recover after the allowed retries.",
                    retryable=False,
                ) from exc
            raise AppError(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_unavailable", "A required provider is unavailable.") from exc

        degraded = []
        pronunciation = None
        try:
            pronunciation = self.pronunciation.assess(PronunciationRequest(
                learner_transcript=stt_result.transcript,
                expected_text=ai_result.corrected_learner_sentence,
                audio_asset_reference=asset.storage_key, level=learner.proficiency_level,
                correlation_id=correlation_id,
            ))
            provider_requests += _provider_request_count(pronunciation)
        except Exception as exc:
            provider_requests += _provider_request_count(exc)
            degraded.append("pronunciation")
        audio_reference = None
        if generate_audio:
            try:
                tts_result = self.tts.synthesize(TextToSpeechRequest(
                    text=ai_result.tutor_message, learner_level=learner.proficiency_level,
                    correlation_id=correlation_id,
                ))
                provider_requests += _provider_request_count(tts_result)
                audio_reference = tts_result.audio_asset_reference
                self._audit("GENERATED_AUDIO_CREATED", learner.id)
            except Exception as exc:
                provider_requests += _provider_request_count(exc)
                degraded.append("text_to_speech")

        ConversationMemoryService(self.session).update(learner.id, [
            MemorySignalInput(category="grammar", value=value)
            for value in ai_result.learning_signals.grammar_focus
        ] + [
            MemorySignalInput(category="vocabulary", value=value)
            for value in ai_result.learning_signals.vocabulary
        ])
        usage.record(
            learner_id=learner.id, user_id=user.id, voice_session_id=voice_session.id,
            provider_kind="voice_pipeline",
            input_units=ai_result.usage.input_units,
            output_units=ai_result.usage.output_units,
            degraded=bool(degraded),
        )
        result = VoiceTutorResult(
            voice_turn_id=turn.id, transcript=stt_result.transcript,
            tutor_text=ai_result.tutor_message,
            corrected_sentence=ai_result.corrected_learner_sentence,
            correction_explanation=ai_result.correction_explanation,
            vocabulary_suggestions=ai_result.vocabulary_suggestions,
            pronunciation_summary="Synthetic practice estimate." if pronunciation else None,
            fluency_summary="Keep a steady pace." if pronunciation else None,
            confidence_encouragement=ai_result.encouragement,
            next_question=ai_result.conversation_question,
            generated_audio_reference=audio_reference,
            assessment_type=pronunciation.assessment_type if pronunciation else None,
            processing_status="PARTIALLY_SUCCEEDED" if degraded else "SUCCEEDED",
            degraded_features=degraded, request_id=request_id, correlation_id=correlation_id,
        )
        attempt.status = result.processing_status
        attempt.result_json = result.model_dump(mode="json")
        attempt.degraded_features = degraded
        attempt.completed_at = datetime.now(timezone.utc)
        try:
            usage.reconcile_provider_call(
                provider_call_id,
                request_count=provider_requests,
                outcome="DEGRADED" if degraded else "SUCCESS",
                failed=bool(degraded),
            )
        except ProviderCallLeaseLost as exc:
            self.session.rollback()
            raise AppError(
                status.HTTP_409_CONFLICT,
                "provider_result_superseded",
                "This provider result arrived after its processing lease expired. Retry safely.",
                retryable=True,
            ) from exc
        self._audit("MEMORY_UPDATED", learner.id)
        self._audit("VOICE_PROCESSING_COMPLETED", learner.id)
        self.session.commit()
        if self.metrics:
            self.metrics.increment("voice_turn_success")
            if degraded: self.metrics.increment("ai_degraded_responses")
        return result
