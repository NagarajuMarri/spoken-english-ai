import logging
from time import perf_counter

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.ai.exceptions import (
    ProviderConnectionError,
    ProviderContextLimit,
    ProviderError,
    ProviderIncompleteResponse,
    ProviderMalformedResponse,
    ProviderOutputInvalid,
    ProviderRateLimited,
    ProviderServiceError,
    ProviderTimeout,
    ProviderUnavailable,
)
from backend.app.ai.models import AIConversationRequest, AIConversationResponse, ConversationHistoryTurn
from backend.app.ai.service import AIConversationService, AdaptivePolicy
from backend.app.conversation_memory.models import MemorySignalInput
from backend.app.conversation_memory.service import ConversationMemoryService
from backend.app.core.errors import AppError
from backend.app.core.operations import enforce_rate_limit
from backend.app.core.security import Principal, current_principal, ensure_owner
from backend.app.db.session import get_db
from backend.app.domain.scenarios import SCENARIOS_BY_ID
from backend.app.models import AICostMetricEvent, AITurnAttempt, Conversation, VoiceProcessingAttempt
from backend.app.intelligent_learning.models import CostEvent
from backend.app.providers.pronunciation.deterministic import DeterministicPronunciationProvider
from backend.app.providers.stt.contracts import SpeechToTextRequest
from backend.app.providers.stt.deterministic import DeterministicSpeechToTextProvider
from backend.app.providers.tts.deterministic import DeterministicTextToSpeechProvider
from backend.app.repositories.conversations import ConversationRepository
from backend.app.repositories.ai_turns import AITurnAttemptRepository
from backend.app.repositories.conversations import TurnSequenceConflict
from backend.app.usage.service import UsageService
from backend.app.voice.models import VoiceTutorResult
from backend.app.voice.orchestration import VoiceTutorOrchestrationService
from backend.app.tutors import get_tutor

router = APIRouter(prefix="/api/v1", tags=["ai-tutor"])
logger = logging.getLogger("spoken_english.ai_turns")


class AITurnCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class AITurnRead(BaseModel):
    tutor_message: str
    corrected_sentence: str | None
    correction_explanation: str | None
    vocabulary_suggestions: list[str]
    next_question: str
    encouragement: str
    adaptive_policy: dict


def _provider_app_error(exc: ProviderError) -> AppError:
    headers = {}
    if exc.retry_after_seconds is not None:
        headers["Retry-After"] = str(exc.retry_after_seconds)
    if isinstance(exc, ProviderTimeout):
        return AppError(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "llm_timeout",
            "The tutor took too long to respond. Retry this turn.",
            headers,
            retryable=True,
        )
    if isinstance(exc, ProviderConnectionError):
        return AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "llm_connection_error",
            "The tutor could not connect to the AI service. Retry this turn.",
            headers,
            retryable=True,
        )
    if isinstance(exc, ProviderRateLimited):
        return AppError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "llm_rate_limited",
            "The AI service is temporarily busy. Wait briefly, then retry this turn.",
            headers,
            retryable=True,
        )
    if isinstance(exc, ProviderServiceError):
        return AppError(
            status.HTTP_502_BAD_GATEWAY,
            "llm_provider_error",
            "The AI service had a temporary error. Retry this turn.",
            headers,
            retryable=True,
        )
    if isinstance(exc, ProviderContextLimit):
        return AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "llm_context_limit",
            "This turn is too long for the tutor. Shorten it and send again.",
            retryable=False,
        )
    if isinstance(exc, ProviderIncompleteResponse):
        return AppError(
            status.HTTP_502_BAD_GATEWAY,
            "llm_incomplete_response",
            "The tutor response ended before it was complete. Retry this turn safely.",
            headers,
            retryable=True,
        )
    if isinstance(exc, ProviderMalformedResponse):
        return AppError(
            status.HTTP_502_BAD_GATEWAY,
            "llm_malformed_response",
            "The tutor returned an incomplete response. Send the turn again.",
            retryable=False,
        )
    if isinstance(exc, ProviderOutputInvalid):
        return AppError(
            status.HTTP_502_BAD_GATEWAY,
            "llm_schema_validation_failed",
            "The tutor response could not be validated. Send the turn again.",
            retryable=False,
        )
    return AppError(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "llm_unavailable",
        "The tutor is temporarily unavailable. Please try again shortly.",
        retryable=False,
    )


def _failure_from_attempt(attempt: AITurnAttempt) -> AppError:
    error_types = {
        "provider_timeout": ProviderTimeout,
        "provider_connection_error": ProviderConnectionError,
        "provider_rate_limit": ProviderRateLimited,
        "provider_service_error": ProviderServiceError,
        "provider_context_limit": ProviderContextLimit,
        "provider_incomplete_response": ProviderIncompleteResponse,
        "provider_malformed_response": ProviderMalformedResponse,
        "provider_schema_validation_failed": ProviderOutputInvalid,
    }
    error_type = error_types.get(attempt.failure_code or "", ProviderUnavailable)
    return _provider_app_error(error_type("Stored provider failure."))


def _api_result(response: AIConversationResponse, policy: AdaptivePolicy) -> dict:
    return {
        "tutor_message": response.tutor_message,
        "corrected_sentence": response.corrected_learner_sentence,
        "correction_explanation": response.correction_explanation,
        "vocabulary_suggestions": response.vocabulary_suggestions,
        "next_question": response.conversation_question,
        "encouragement": response.encouragement,
        "adaptive_policy": policy.__dict__,
    }


class VoiceProcessRequest(BaseModel):
    generate_audio: bool = True


class VoiceTranscriptionRead(BaseModel):
    transcript: str
    detected_language: str
    duration_ms: int
    size_bytes: int


@router.post("/conversations/{conversation_id}/ai-turns", response_model=AITurnRead)
def ai_turn(
    conversation_id: str,
    data: AITurnCreate,
    request: Request,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=100,
    ),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    enforce_rate_limit(request, "authenticated_burst", principal.user.id)
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "conversation_not_found", "Conversation not found.")
    ensure_owner(conversation.learner_id, principal)
    usage = UsageService(session)
    tutor = get_tutor(principal.learner.preferred_tutor_id or "ananya")
    provider = request.app.state.llm_provider
    turn_key = idempotency_key or request.state.request_id
    attempts = AITurnAttemptRepository(session)
    attempt = attempts.get(conversation.id, turn_key)
    response = None
    needs_provider = False
    if attempt is not None:
        if attempt.learner_id != principal.learner.id or attempt.learner_text != data.message:
            raise AppError(
                status.HTTP_409_CONFLICT,
                "ai_turn_idempotency_conflict",
                "This retry identity belongs to a different learner turn.",
                retryable=False,
            )
        if attempt.status == "COMPLETED":
            return attempt.result_json["api_result"]
        if attempt.status == "PROVIDER_SUCCEEDED":
            response = AIConversationResponse.model_validate(attempt.result_json["provider_response"])
        elif attempt.status == "FAILED_FINAL":
            raise _failure_from_attempt(attempt)
        elif attempt.status == "IN_PROGRESS":
            raise AppError(
                status.HTTP_409_CONFLICT,
                "ai_turn_in_progress",
                "This tutor turn is already being processed.",
                retryable=True,
            )
        else:
            needs_provider = True
    else:
        needs_provider = True

    if needs_provider:
        usage.enforce(principal.learner.id, principal.user.id)
        if provider is None:
            raise AppError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "llm_unavailable",
                "The tutor is temporarily unavailable. Please try again shortly.",
                retryable=True,
            )
        if attempt is not None:
            attempts.mark_in_progress(attempt)
        else:
            try:
                attempt = attempts.create(
                    conversation_id=conversation.id,
                    learner_id=principal.learner.id,
                    idempotency_key=turn_key,
                    learner_text=data.message,
                )
            except IntegrityError as exc:
                session.rollback()
                raise AppError(
                    status.HTTP_409_CONFLICT,
                    "ai_turn_in_progress",
                    "This tutor turn is already being processed.",
                    retryable=True,
                ) from exc

    if attempt is None:
        raise AppError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "ai_turn_state_lost",
            "The tutor turn could not be created. Send it again.",
            retryable=False,
        )

    started_at = perf_counter()
    if response is None:
        try:
            response = AIConversationService(provider).generate(AIConversationRequest(
                learner_id=principal.learner.id,
                conversation_id=conversation.id,
                learner_level=principal.learner.proficiency_level,
                preferred_language=(
                    principal.learner.native_language
                    if principal.learner.telugu_explanations_enabled
                    else "English"
                ),
                tutor_id=tutor.tutor_id,
                tutor_prompt_profile=tutor.prompt_profile,
                tutor_vocabulary_profile=tutor.vocabulary_profile,
                scenario=conversation.scenario_id,
                topic=SCENARIOS_BY_ID[conversation.scenario_id].name,
                conversation_history=[
                    ConversationHistoryTurn(
                        learner_message=item.learner_text,
                        tutor_message=item.tutor_response,
                    )
                    for item in conversation.messages[-3:]
                ],
                current_learner_message=data.message,
                correlation_id=request.state.correlation_id,
            ))
        except ProviderError as exc:
            session.rollback()
            attempt = attempts.get(conversation.id, turn_key)
            if attempt is None:
                raise AppError(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "ai_turn_state_lost",
                    "The tutor turn could not be recovered. Send it again.",
                    retryable=False,
                ) from exc
            attempts.mark_provider_failure(attempt, exc)
            usage.record_failure_attempt(
                ai_turn_attempt_id=attempt.id,
                learner_id=principal.learner.id,
                user_id=principal.user.id,
                provider_requests=exc.provider_requests,
                input_units=exc.input_units,
                output_units=exc.output_units,
                commit=False,
            )
            session.commit()
            logger.warning(
                "llm_provider_failure request_id=%s attempt_id=%s failure_code=%s "
                "provider_requests=%s retryable=%s",
                request.state.request_id,
                attempt.id,
                exc.failure_code,
                exc.provider_requests,
                exc.retryable,
            )
            request.app.state.metrics.increment(
                "ai_provider_timeouts"
                if isinstance(exc, ProviderTimeout)
                else "ai_provider_failures"
            )
            raise _provider_app_error(exc) from exc
        attempts.checkpoint_provider_success(
            attempt,
            response,
            provider_latency_ms=(perf_counter() - started_at) * 1000,
        )

    latency_ms = float(
        attempt.result_json.get("provider_latency_ms", (perf_counter() - started_at) * 1000)
    )
    cached_input = min(response.usage.cached_input_units, response.usage.input_units)
    uncached_input = response.usage.input_units - cached_input
    estimated_cost_usd = (
        uncached_input * request.app.state.settings.openai_llm_input_usd_per_million
        + cached_input * request.app.state.settings.openai_llm_cached_input_usd_per_million
        + response.usage.output_units * request.app.state.settings.openai_llm_output_usd_per_million
    ) / 1_000_000
    cost_event = CostEvent(
        learner_id=principal.learner.id,
        lesson_id=conversation.scenario_id,
        conversation_id=conversation.id,
        prompt_tokens=int(response.usage.input_units),
        completion_tokens=int(response.usage.output_units),
        estimated_cost_usd=estimated_cost_usd,
        response_latency_ms=latency_ms,
        cache_hit=False,
        model_used=response.provider_metadata_reference,
        cached_tokens=cached_input,
        cost_classification="ESTIMATE_FROM_PROVIDER_REPORTED_USAGE",
    )
    policy = AdaptivePolicy.decide(level=principal.learner.proficiency_level, correctness=0.7, repeated_mistakes=1, confidence=60)
    result = _api_result(response, policy)
    try:
        session.add(AICostMetricEvent(
            ai_turn_attempt_id=attempt.id,
            learner_id=principal.learner.id,
            lesson_id=conversation.scenario_id,
            conversation_id=conversation.id,
            prompt_tokens=int(response.usage.input_units),
            completion_tokens=int(response.usage.output_units),
            cached_tokens=cached_input,
            estimated_cost_usd=estimated_cost_usd,
            response_latency_ms=latency_ms,
            cache_hit=False,
            model_used=response.provider_metadata_reference,
            cost_classification="ESTIMATE_FROM_PROVIDER_REPORTED_USAGE",
        ))
        ConversationRepository(session).add_message(
            conversation.id,
            data.message,
            response.tutor_message,
            response.correction_explanation,
            ai_turn_attempt_id=attempt.id,
            commit=False,
        )
        ConversationMemoryService(session).update(
            principal.learner.id,
            [
                MemorySignalInput(category="grammar", value=value)
                for value in response.learning_signals.grammar_focus
            ] + [
                MemorySignalInput(category="vocabulary", value=value)
                for value in response.learning_signals.vocabulary
            ],
            commit=False,
        )
        usage.record(
            ai_turn_attempt_id=attempt.id,
            learner_id=principal.learner.id,
            user_id=principal.user.id,
            provider_kind="llm",
            outcome="SUCCESS",
            request_count=response.usage.provider_requests,
            retries=max(0, response.usage.provider_requests - 1),
            input_units=response.usage.input_units,
            output_units=response.usage.output_units,
            commit=False,
        )
        attempts.mark_completed(attempt, result)
        session.commit()
    except (SQLAlchemyError, TurnSequenceConflict) as exc:
        session.rollback()
        recovered = attempts.get(conversation.id, turn_key)
        if recovered is not None and recovered.status == "COMPLETED":
            return recovered.result_json["api_result"]
        logger.error(
            "llm_persistence_failure request_id=%s attempt_id=%s",
            request.state.request_id,
            attempt.id,
        )
        raise AppError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "llm_persistence_failed",
            "The tutor answered, but the turn could not be saved. Retry this turn safely.",
            retryable=True,
        ) from exc

    request.app.state.learning_engine.metrics.record(cost_event)
    request.app.state.metrics.increment("ai_requests")
    return result


@router.post("/conversations/{conversation_id}/transcriptions", response_model=VoiceTranscriptionRead)
async def transcribe_voice_input(
    conversation_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    """Transcribe one bounded browser capture without retaining raw audio."""
    enforce_rate_limit(request, "voice_turn", principal.user.id)
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "conversation_not_found", "Conversation not found.")
    ensure_owner(conversation.learner_id, principal)
    if request.headers.get("x-voice-processing-consent", "").lower() != "accepted":
        raise AppError(
            status.HTTP_403_FORBIDDEN,
            "voice_consent_required",
            "Voice-processing consent is required.",
        )

    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    allowed_types = {"audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "audio/mpeg"}
    if content_type not in allowed_types:
        raise AppError(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported_audio_type", "Unsupported audio format.")
    try:
        duration_ms = int(request.headers.get("x-audio-duration-ms", "0"))
    except ValueError as exc:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_audio_duration", "Invalid audio duration.") from exc
    if not 100 <= duration_ms <= 60_000:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_audio_duration",
            "Audio duration must be between 0.1 and 60 seconds.",
        )

    audio = await request.body()
    if not audio:
        raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty_audio", "No audio was captured.")
    if len(audio) > request.app.state.settings.upload_size_limit_bytes:
        raise AppError(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "audio_too_large", "Audio capture is too large.")
    provider = request.app.state.speech_to_text_provider
    if provider is None:
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "speech_to_text_unavailable",
            "Speech recognition is unavailable.",
        )

    extension = {
        "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a",
        "audio/wav": "wav", "audio/mpeg": "mp3",
    }[content_type]
    stt_request = SpeechToTextRequest(
        audio_asset_reference=f"ephemeral/{request.state.request_id}.{extension}",
        audio_bytes=audio,
        filename=f"speech.{extension}",
        content_type=content_type,
        learner_id=principal.learner.id,
        voice_session_id=conversation.id,
        voice_turn_id=request.state.request_id,
        correlation_id=request.state.correlation_id,
        maximum_duration_seconds=60,
        duration_seconds=duration_ms / 1000,
        size_bytes=len(audio),
    )
    try:
        result = await run_in_threadpool(provider.transcribe, stt_request)
    except ValueError as exc:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "no_speech_detected",
            "No clear speech was detected.",
        ) from exc
    except ProviderTimeout as exc:
        raise AppError(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "speech_to_text_timeout",
            "Speech recognition timed out.",
        ) from exc
    except ProviderUnavailable as exc:
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "speech_to_text_unavailable",
            "Speech recognition is unavailable.",
        ) from exc

    transcript = result.transcript.strip()
    if not transcript:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "no_speech_detected",
            "No clear speech was detected.",
        )
    request.app.state.metrics.increment("voice_transcriptions_completed")
    request.app.state.metrics.observe("voice_capture_size_bytes", len(audio))
    return {
        "transcript": transcript,
        "detected_language": result.detected_language,
        "duration_ms": duration_ms,
        "size_bytes": len(audio),
    }


@router.get("/learners/{learner_id}/memory")
def memory(learner_id: str, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    ensure_owner(learner_id, principal)
    return ConversationMemoryService(session).export(learner_id)


@router.delete("/learners/{learner_id}/memory")
def delete_memory(learner_id: str, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    ensure_owner(learner_id, principal)
    return {"deleted_signals": ConversationMemoryService(session).delete(learner_id)}


@router.get("/learners/{learner_id}/ai-usage")
def ai_usage(learner_id: str, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    ensure_owner(learner_id, principal)
    return UsageService(session).summary(learner_id)


@router.post("/learners/{learner_id}/daily-plan/generate")
def generate_daily_plan(learner_id: str, principal: Principal = Depends(current_principal)):
    ensure_owner(learner_id, principal)
    return {
        "conversation_topic": "Daily routine",
        "speaking_objective": "Describe a normal day clearly.",
        "key_vocabulary": ["usually", "afterwards", "routine"],
        "grammar_focus": "present simple",
        "pronunciation_focus": "sentence stress",
        "short_practice": "Describe your morning in three sentences.",
        "revision_item": "time expressions",
        "homework": "Record a one-minute daily-routine practice.",
        "success_criteria": ["three complete sentences", "one sequencing word"],
        "expected_duration_minutes": min(15, principal.learner.daily_goal_minutes),
        "generation_mode": "deterministic_fallback",
    }


@router.post("/voice-sessions/{session_id}/turns/{turn_id}/process", response_model=VoiceTutorResult)
def process_voice_turn(
    session_id: str,
    turn_id: str,
    data: VoiceProcessRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=100),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    enforce_rate_limit(request, "voice_turn", principal.user.id)
    service = VoiceTutorOrchestrationService(
        session,
        stt=DeterministicSpeechToTextProvider(),
        ai=DeterministicAIProvider(),
        pronunciation=DeterministicPronunciationProvider(),
        tts=DeterministicTextToSpeechProvider(),
        metrics=request.app.state.metrics,
    )
    return service.process(
        turn_id=turn_id, learner=principal.learner, user=principal.user,
        idempotency_key=idempotency_key, correlation_id=request.state.correlation_id,
        request_id=request.state.request_id, generate_audio=data.generate_audio,
    )


@router.get("/voice-sessions/{session_id}/turns/{turn_id}/result", response_model=VoiceTutorResult)
def voice_turn_result(
    session_id: str, turn_id: str,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    attempt = session.scalar(select(VoiceProcessingAttempt).where(
        VoiceProcessingAttempt.voice_turn_id == turn_id,
        VoiceProcessingAttempt.learner_id == principal.learner.id,
        VoiceProcessingAttempt.status.in_(["SUCCEEDED", "PARTIALLY_SUCCEEDED"]),
    ).order_by(VoiceProcessingAttempt.completed_at.desc()).limit(1))
    if attempt is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "voice_result_not_found", "Voice result not found.")
    return attempt.result_json
