from datetime import datetime, timezone
from sqlalchemy import select

from backend.app.ai.models import AIConversationRequest
from backend.app.ai.service import AIConversationService
from backend.app.conversation_memory.models import MemorySignalInput
from backend.app.conversation_memory.service import ConversationMemoryService
from backend.app.core.errors import AppError
from backend.app.models import (
    AudioAsset, ConsentRecord, SecurityAuditEvent, VoiceProcessingAttempt, VoiceSession, VoiceTurn,
)
from backend.app.providers.pronunciation.contracts import PronunciationRequest
from backend.app.providers.stt.contracts import SpeechToTextRequest
from backend.app.providers.tts.contracts import TextToSpeechRequest
from backend.app.usage.service import UsageService
from backend.app.voice.models import VoiceTutorResult
from fastapi import status


class VoiceTutorOrchestrationService:
    """STT and AI are fatal; pronunciation and TTS degrade independently."""

    def __init__(self, session, *, stt, ai, pronunciation, tts, metrics=None):
        self.session = session
        self.stt = stt
        self.ai = AIConversationService(ai)
        self.pronunciation = pronunciation
        self.tts = tts
        self.metrics = metrics

    def _audit(self, event_type, learner_id, outcome="SUCCEEDED", reason=None):
        self.session.add(SecurityAuditEvent(
            event_type=event_type, learner_id=learner_id, outcome=outcome,
            reason_code=reason, metadata_json={},
        ))

    def process(self, *, turn_id, learner, user, idempotency_key, correlation_id, request_id=None, generate_audio=True):
        existing = self.session.scalar(select(VoiceProcessingAttempt).where(
            VoiceProcessingAttempt.voice_turn_id == turn_id,
            VoiceProcessingAttempt.idempotency_key == idempotency_key,
        ))
        if existing and existing.status in {"SUCCEEDED", "PARTIALLY_SUCCEEDED"}:
            return VoiceTutorResult.model_validate(existing.result_json)

        turn = self.session.get(VoiceTurn, turn_id)
        if turn is None:
            raise AppError(status.HTTP_404_NOT_FOUND, "voice_turn_not_found", "Voice turn not found.")
        voice_session = self.session.get(VoiceSession, turn.voice_session_id)
        if voice_session.learner_id != learner.id:
            raise AppError(status.HTTP_404_NOT_FOUND, "resource_not_found", "Resource not found.")
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
        usage.enforce(learner.id, user.id, voice_session.id)
        attempt = existing or VoiceProcessingAttempt(
            voice_turn_id=turn.id, learner_id=learner.id,
            idempotency_key=idempotency_key, status="PROCESSING",
        )
        self.session.add(attempt)
        self._audit("VOICE_PROCESSING_STARTED", learner.id)
        self.session.commit()

        try:
            stt_result = self.stt.transcribe(SpeechToTextRequest(
                audio_asset_reference=asset.storage_key, content_type=asset.media_type,
                learner_id=learner.id, voice_session_id=voice_session.id,
                voice_turn_id=turn.id, correlation_id=correlation_id,
                duration_seconds=1,
            ))
            ai_result = self.ai.generate(AIConversationRequest(
                learner_id=learner.id, conversation_id=voice_session.id,
                learner_level=learner.proficiency_level, preferred_language=learner.native_language,
                scenario=voice_session.scenario_id, topic=voice_session.scenario_id,
                conversation_history=[], current_learner_message=stt_result.transcript,
                correlation_id=correlation_id,
            ))
        except Exception as exc:
            attempt.status = "RETRYABLE_FAILURE"
            attempt.failure_code = "provider_unavailable"
            self._audit("PROVIDER_FAILED", learner.id, "FAILED", "provider_unavailable")
            self.session.commit()
            if self.metrics: self.metrics.increment("voice_turn_failures")
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
        except Exception:
            degraded.append("pronunciation")
        audio_reference = None
        if generate_audio:
            try:
                tts_result = self.tts.synthesize(TextToSpeechRequest(
                    text=ai_result.tutor_message, learner_level=learner.proficiency_level,
                    correlation_id=correlation_id,
                ))
                audio_reference = tts_result.audio_asset_reference
                self._audit("GENERATED_AUDIO_CREATED", learner.id)
            except Exception:
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
        self._audit("MEMORY_UPDATED", learner.id)
        self._audit("VOICE_PROCESSING_COMPLETED", learner.id)
        self.session.commit()
        if self.metrics:
            self.metrics.increment("voice_turn_success")
            if degraded: self.metrics.increment("ai_degraded_responses")
        return result
