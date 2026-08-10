import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from math import ceil, isfinite
from time import perf_counter
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.ai.exceptions import (
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderContextLimit,
    ProviderError,
    ProviderIncompleteResponse,
    ProviderMalformedResponse,
    ProviderOutputInvalid,
    ProviderRateLimited,
    ProviderRefusal,
    ProviderServiceError,
    ProviderTimeout,
    ProviderUnavailable,
)
from backend.app.ai.models import AIConversationRequest, AIConversationResponse, ConversationHistoryTurn
from backend.app.ai.output_safety import (
    enforce_api_result_output_safety,
    enforce_response_output_safety,
    normalize_spoken_output,
)
from backend.app.ai.service import AIConversationService, AdaptivePolicy
from backend.app.commercial.runtime import RuntimeEntitlementService
from backend.app.conversation_memory.models import MemorySignalInput
from backend.app.conversation_memory.service import ConversationMemoryService
from backend.app.core.errors import AppError
from backend.app.core.operations import enforce_rate_limit, record_stage_timing
from backend.app.core.security import Principal, current_principal, ensure_owner
from backend.app.db.session import get_db
from backend.app.domain.scenarios import SCENARIOS_BY_ID
from backend.app.models import (
    AICostMetricEvent,
    AITurnAttempt,
    Conversation,
    ProviderCallEvent,
    VoiceProcessingAttempt,
    VoiceTranscriptionAttempt,
)
from backend.app.intelligent_learning.models import CostEvent
from backend.app.providers.pronunciation.deterministic import DeterministicPronunciationProvider
from backend.app.providers.stt.contracts import SpeechToTextRequest
from backend.app.providers.stt.deterministic import DeterministicSpeechToTextProvider
from backend.app.providers.tts.deterministic import DeterministicTextToSpeechProvider
from backend.app.providers.tts.contracts import TextToSpeechRequest
from backend.app.repositories.conversations import ConversationRepository
from backend.app.repositories.ai_turns import AITurnAttemptRepository
from backend.app.repositories.tts_synthesis import TTSSynthesisRepository
from backend.app.repositories.conversations import TurnSequenceConflict
from backend.app.usage.service import ProviderCallLeaseLost, UsageService
from backend.app.usage.limits import UsageLimits
from backend.app.voice.models import VoiceTutorResult
from backend.app.voice.orchestration import VoiceTutorOrchestrationService
from backend.app.tutors import get_tutor
from backend.app.domain.enums import LanguageMode
from backend.app.language_review.models import LanguageReviewResult
from backend.app.language_review.service import LanguageReviewService, degraded_review_result
from backend.app.coaching import (
    LearnerIntent,
    apply_pedagogy_guardrails,
    build_coaching_outcome,
    classify_learner_intent,
    correction_reexplanation_input,
    protect_learner_facts,
    tutor_input_for_retry,
)
from backend.app.transcript_safety import (
    UnusableTranscript,
    normalize_known_tutor_reference,
    safe_transcript,
)
from backend.app.explanation_language import (
    ExplanationLanguage,
    ExplanationLanguageState,
    explanation_policy_instruction,
    resolve_explanation_language,
)

router = APIRouter(prefix="/api/v1", tags=["ai-tutor"])
logger = logging.getLogger("spoken_english.ai_turns")


class AITurnCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    input_source: str = Field(default="TEXT", pattern="^(TEXT|VOICE)$")
    detected_language: str | None = Field(default=None, max_length=20)
    stt_confidence: float | None = Field(default=None, ge=0, le=1)


class AITurnRead(BaseModel):
    turn_id: str
    tutor_message: str
    correction_type: str
    corrected_sentence: str | None
    incorrect_span: str | None
    corrected_form: str | None
    correction_explanation: str | None
    correction_explanation_default: str | None
    vocabulary_suggestions: list[str]
    next_question: str
    encouragement: str
    adaptive_policy: dict
    language_mode: LanguageMode
    review_changed: bool
    review_reason_code: str
    preserved_learning_terms: list[str]
    expression_hint: str
    telugu_explanation: str | None
    language_review_status: str
    language_review_failure_code: str | None
    spoken_text: str
    coaching_mode: str
    coaching_state: str
    retry_of_turn_id: str | None
    explanation_language: ExplanationLanguage
    explanation_language_state: ExplanationLanguageState
    learner_intent: LearnerIntent


_ARABIC_SCRIPT = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")


def _unexpected_foreign_script(text: str) -> bool:
    return bool(_ARABIC_SCRIPT.search(text))


def _primary_language(value: str | None) -> str:
    return (value or "").casefold().replace("_", "-").split("-", 1)[0]


def _expects_telugu(learner, detected_language: str | None = None) -> bool:
    return (
        str(learner.native_language).casefold() == "telugu"
        or LanguageMode(learner.language_mode or "ENGLISH") != LanguageMode.ENGLISH
        or _primary_language(detected_language) in {"te", "tel", "telugu"}
    )


def _tutor_input(message: str, *, input_source: str, stt_confidence: float | None) -> str:
    if input_source == "VOICE" and (
        _unexpected_foreign_script(message)
        or (stt_confidence is not None and stt_confidence < 0.55)
    ):
        return (
            "The latest speech transcript is inconsistent with this English-training session and may "
            "be a recognition error. Do not switch language or topic. Briefly ask the learner to repeat "
            "what they meant in English."
        )
    return message


def _provider_app_error(exc: ProviderError) -> AppError:
    headers = {}
    if exc.retry_after_seconds is not None:
        headers["Retry-After"] = str(exc.retry_after_seconds)
    if isinstance(exc, ProviderConfigurationError):
        return AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "llm_provider_not_configured",
            "The tutor language service is not configured. Contact support.",
            retryable=False,
        )
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
            status.HTTP_422_UNPROCESSABLE_CONTENT,
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
    if isinstance(exc, ProviderRefusal):
        return AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "llm_refused",
            "The tutor cannot answer this request. Rephrase it and send again.",
            retryable=False,
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


def _validated_api_result(
    result: dict,
    language_mode: LanguageMode,
) -> dict:
    try:
        return enforce_api_result_output_safety(result, language_mode)
    except ProviderOutputInvalid as exc:
        raise _provider_app_error(exc) from exc


def _completed_api_result(
    attempt: AITurnAttempt,
    fallback_language_mode: LanguageMode,
) -> dict:
    raw_result = attempt.result_json.get("api_result")
    if not isinstance(raw_result, dict):
        raise _provider_app_error(ProviderOutputInvalid(
            "Stored tutor output is invalid.",
            schema_path="api_result",
        ))
    result = dict(raw_result)
    raw_language_mode = result.get("language_mode", fallback_language_mode.value)
    try:
        language_mode = LanguageMode(raw_language_mode)
    except (TypeError, ValueError) as exc:
        invalid = ProviderOutputInvalid(
            "Stored tutor output is invalid.",
            schema_path="language_mode",
        )
        raise _provider_app_error(invalid) from exc
    result.setdefault("language_mode", language_mode.value)
    result.setdefault("turn_id", attempt.id)
    return _validated_api_result(result, language_mode)


def _failure_from_attempt(attempt: AITurnAttempt, *, language_review: bool = False) -> AppError:
    if attempt.failure_code == "provider_retry_limit_reached":
        return AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "llm_retry_limit_reached",
            "The tutor could not recover after the allowed retries.",
            retryable=False,
        )
    error_types = {
        "provider_timeout": ProviderTimeout,
        "provider_connection_error": ProviderConnectionError,
        "provider_rate_limit": ProviderRateLimited,
        "provider_service_error": ProviderServiceError,
        "provider_context_limit": ProviderContextLimit,
        "provider_incomplete_response": ProviderIncompleteResponse,
        "provider_refusal": ProviderRefusal,
        "provider_malformed_response": ProviderMalformedResponse,
        "provider_schema_validation_failed": ProviderOutputInvalid,
        "provider_configuration_error": ProviderConfigurationError,
    }
    error_type = error_types.get(attempt.failure_code or "", ProviderUnavailable)
    error = error_type("Stored provider failure.")
    return _language_review_app_error(error) if language_review else _provider_app_error(error)


def _api_result(
    response: AIConversationResponse,
    policy: AdaptivePolicy,
    turn_id: str,
    review: LanguageReviewResult,
    coaching,
    language_decision,
    previous_result: dict | None,
    learner_intent: LearnerIntent,
) -> dict:
    default_correction_explanation = response.correction_explanation
    if coaching.state in {"WAITING_FOR_RETRY", "EXPLAINING_CORRECTION"}:
        default_correction_explanation = (
            default_correction_explanation
            or (previous_result or {}).get("correction_explanation_default")
            or (previous_result or {}).get("correction_explanation")
        )
    if language_decision.state == ExplanationLanguageState.ONE_TURN_OVERRIDE:
        default_correction_explanation = (
            (previous_result or {}).get("correction_explanation_default")
            or (previous_result or {}).get("correction_explanation")
            or response.correction_explanation
        )
    result = {
        "turn_id": turn_id,
        "tutor_message": response.tutor_message,
        "correction_type": response.correction_type,
        "corrected_sentence": response.corrected_learner_sentence,
        "incorrect_span": coaching.incorrect_span,
        "corrected_form": coaching.corrected_form,
        "correction_explanation": response.correction_explanation,
        "correction_explanation_default": default_correction_explanation,
        "vocabulary_suggestions": response.vocabulary_suggestions,
        "next_question": response.conversation_question,
        "encouragement": response.encouragement,
        "adaptive_policy": policy.__dict__,
        "language_mode": review.language_mode,
        "review_changed": review.review_changed,
        "review_reason_code": review.review_reason_code,
        "preserved_learning_terms": review.preserved_learning_terms,
        "expression_hint": review.expression_hint,
        "telugu_explanation": (
            response.correction_explanation
            if review.language_mode != LanguageMode.ENGLISH
            else None
        ),
        "language_review_status": review.status,
        "language_review_failure_code": review.failure_code,
        "spoken_text": coaching.spoken_text,
        "coaching_mode": coaching.mode,
        "coaching_state": coaching.state,
        "retry_of_turn_id": coaching.retry_of_turn_id,
        "explanation_language": language_decision.language,
        "explanation_language_state": language_decision.state,
        "learner_intent": learner_intent,
    }
    return _validated_api_result(result, review.language_mode)


def _language_review_app_error(exc: ProviderError) -> AppError:
    base = _provider_app_error(exc)
    code = {
        "llm_timeout": "language_review_timeout",
        "llm_connection_error": "language_review_connection_error",
        "llm_rate_limited": "language_review_rate_limited",
        "llm_provider_error": "language_review_provider_error",
        "llm_context_limit": "language_review_context_limit",
        "llm_incomplete_response": "language_review_incomplete",
        "llm_refused": "language_review_refused",
        "llm_malformed_response": "language_review_malformed",
        "llm_schema_validation_failed": "language_review_validation_failed",
        "llm_unavailable": "language_review_unavailable",
        "llm_provider_not_configured": "language_review_provider_not_configured",
    }.get(base.code, "language_review_unavailable")
    return AppError(
        base.status_code,
        code,
        "The native-language review could not be completed. Retry this turn safely.",
        base.headers,
        retryable=base.retryable,
    )


class VoiceProcessRequest(BaseModel):
    generate_audio: bool = True


class VoiceTranscriptionRead(BaseModel):
    transcript: str
    detected_language: str
    confidence: float | None
    duration_ms: int
    size_bytes: int


_TRANSCRIPTION_RESERVATION_MS = 60_000
_PROVIDER_LEASE = timedelta(minutes=5)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _reconcile_provider_call(usage: UsageService, event_id: str, **values):
    try:
        return usage.reconcile_provider_call(event_id, **values)
    except ProviderCallLeaseLost as exc:
        usage.session.rollback()
        raise AppError(
            status.HTTP_409_CONFLICT,
            "provider_result_superseded",
            "This provider result arrived after its processing lease expired. Retry safely.",
            retryable=True,
        ) from exc


def _recover_stale_provider_claim(
    session: Session,
    attempt,
    *,
    transitions: dict[str, str],
    maximum_provider_requests: int | None = None,
) -> None:
    target = transitions.get(attempt.status)
    cutoff = datetime.now(UTC) - _PROVIDER_LEASE
    if target is None or _as_utc(attempt.updated_at) > cutoff:
        return
    failure_code = "provider_lease_expired"
    if (
        maximum_provider_requests is not None
        and attempt.provider_requests >= maximum_provider_requests
    ):
        target = "FAILED_FINAL"
        failure_code = "provider_retry_limit_reached"
    reserved_event_ids = list(session.scalars(
        select(ProviderCallEvent.id).where(
            ProviderCallEvent.attempt_reference == attempt.id,
            ProviderCallEvent.outcome == "RESERVED",
        )
    ))
    if reserved_event_ids:
        fenced_events = cast(CursorResult[Any], session.execute(
            update(ProviderCallEvent)
            .where(
                ProviderCallEvent.id.in_(reserved_event_ids),
                ProviderCallEvent.outcome == "RESERVED",
            )
            .values(
                outcome="FAILURE",
                failed=True,
                completed_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session=False)
        )).rowcount
        if fenced_events != len(reserved_event_ids):
            session.rollback()
            session.refresh(attempt)
            return
    recovered = cast(CursorResult[Any], session.execute(
        update(type(attempt))
        .where(
            type(attempt).id == attempt.id,
            type(attempt).status == attempt.status,
            type(attempt).updated_at <= cutoff,
        )
        .values(
            status=target,
            failure_code=failure_code,
            updated_at=datetime.now(UTC),
        )
        .execution_options(synchronize_session=False)
    )).rowcount == 1
    if recovered:
        session.commit()
        session.refresh(attempt)
    elif reserved_event_ids:
        session.rollback()
        session.refresh(attempt)


def _transcription_attempt_outcome(attempt: VoiceTranscriptionAttempt) -> dict | None:
    if attempt.status == "COMPLETED":
        return dict(attempt.result_json)
    if attempt.status == "IN_PROGRESS":
        raise AppError(
            status.HTTP_409_CONFLICT,
            "speech_to_text_in_progress",
            "This voice capture is already being transcribed.",
            retryable=True,
        )
    if attempt.status == "REJECTED_FINAL":
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "no_speech_detected",
            "No clear speech was detected.",
            retryable=False,
        )
    if attempt.status == "FAILED_FINAL":
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "speech_to_text_retry_limit_reached",
            "Speech recognition could not recover after the allowed retries.",
            retryable=False,
        )
    return None


def _ensure_transcription_identity(
    attempt: VoiceTranscriptionAttempt,
    *,
    learner_id: str,
    audio_digest: str,
    content_type: str,
) -> None:
    if (
        attempt.learner_id != learner_id
        or attempt.audio_digest != audio_digest
        or attempt.content_type != content_type
    ):
        raise AppError(
            status.HTTP_409_CONFLICT,
            "speech_to_text_idempotency_conflict",
            "This retry identity belongs to a different voice capture.",
            retryable=False,
        )


def _authoritative_duration_ms(duration_seconds: float) -> int:
    if not isfinite(duration_seconds) or duration_seconds <= 0:
        return _TRANSCRIPTION_RESERVATION_MS
    return min(_TRANSCRIPTION_RESERVATION_MS, max(100, ceil(duration_seconds * 1000)))


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
    default_language_mode = LanguageMode(principal.learner.language_mode or "ENGLISH")
    expected_language = None
    if data.input_source == "VOICE" and _expects_telugu(principal.learner, data.detected_language):
        expected_language = "te"
    try:
        learner_message = safe_transcript(data.message, expected_language=expected_language)
        if (
            data.input_source == "VOICE"
            and (principal.learner.preferred_tutor_id or "ananya").casefold() == "ananya"
        ):
            learner_message = normalize_known_tutor_reference(
                learner_message,
                confidence=data.stt_confidence,
            )
        if data.input_source == "VOICE" and data.stt_confidence is not None and data.stt_confidence < 0.2:
            raise UnusableTranscript("Speech confidence is too low.")
    except UnusableTranscript as exc:
        learner_message_error = (
            "No clear learner speech was detected. Please try again."
            if data.input_source == "VOICE"
            else "This message contains unsupported or malformed text. Please edit it and try again."
        )
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unusable_transcript" if data.input_source == "VOICE" else "invalid_learner_message",
            learner_message_error,
        ) from exc
    usage = UsageService(session)
    tutor = get_tutor(principal.learner.preferred_tutor_id or "ananya")
    provider = request.app.state.llm_provider
    turn_key = idempotency_key or request.state.request_id
    attempts = AITurnAttemptRepository(session)
    previous_attempt = attempts.latest_completed(conversation.id)
    previous_result = (
        _completed_api_result(previous_attempt, default_language_mode)
        if previous_attempt is not None else None
    )
    learner_intent = classify_learner_intent(learner_message, previous_result)
    language_decision = resolve_explanation_language(learner_message, default_language_mode)
    if language_decision.persist_mode is not None:
        principal.learner.language_mode = language_decision.persist_mode.value
        principal.learner.telugu_explanations_enabled = False
    attempt = attempts.get(conversation.id, turn_key)
    content_response = None
    response = None
    review_result = None
    needs_provider = False
    if attempt is not None:
        if attempt.learner_id != principal.learner.id or attempt.learner_text != learner_message:
            raise AppError(
                status.HTTP_409_CONFLICT,
                "ai_turn_idempotency_conflict",
                "This retry identity belongs to a different learner turn.",
                retryable=False,
            )
        _recover_stale_provider_claim(
            session,
            attempt,
            transitions={
                "IN_PROGRESS": "FAILED_RETRYABLE",
                "REVIEW_IN_PROGRESS": "REVIEW_FAILED_RETRYABLE",
            },
        )
        if attempt.status == "COMPLETED":
            return _completed_api_result(attempt, default_language_mode)
        try:
            if attempt.status in {"PROVIDER_SUCCEEDED", "REVIEW_FAILED_RETRYABLE"}:
                content_response = AIConversationResponse.model_validate(
                    attempt.result_json["provider_response"]
                )
            elif attempt.status == "REVIEW_SUCCEEDED":
                content_response = AIConversationResponse.model_validate(
                    attempt.result_json["provider_response"]
                )
                response = AIConversationResponse.model_validate(
                    attempt.result_json["reviewed_response"]
                )
                review_result = LanguageReviewResult.model_validate(
                    attempt.result_json["language_review"]
                )
        except (KeyError, TypeError, ValueError) as exc:
            invalid = ProviderOutputInvalid(
                "Stored tutor checkpoint is invalid.",
                schema_path="stored_checkpoint",
            )
            raise _provider_app_error(invalid) from exc
        if attempt.status in {"PROVIDER_SUCCEEDED", "REVIEW_FAILED_RETRYABLE", "REVIEW_SUCCEEDED"}:
            pass
        elif attempt.status == "FAILED_FINAL":
            raise _failure_from_attempt(attempt)
        elif attempt.status == "REVIEW_FAILED_FINAL":
            raise _failure_from_attempt(attempt, language_review=True)
        elif attempt.status in {"IN_PROGRESS", "REVIEW_IN_PROGRESS"}:
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

    if needs_provider and provider is None:
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "llm_unavailable",
            "The tutor is temporarily unavailable. Please try again shortly.",
            retryable=True,
        )
    if needs_provider:
        RuntimeEntitlementService(
            session,
            request.app.state.commercial_service.config,
        ).enforce_ai_request(principal.learner.id, new_request=attempt is None)

    provider_call_id = None
    maximum_provider_requests = UsageLimits().maximum_provider_retries + 1
    if needs_provider:
        usage.enforce(principal.learner.id, principal.user.id)
        try:
            if attempt is not None:
                if not attempts.claim_provider_retry(
                    attempt,
                    maximum_provider_requests=maximum_provider_requests,
                    commit=False,
                ):
                    session.rollback()
                    session.refresh(attempt)
                    if (
                        attempt.status == "FAILED_RETRYABLE"
                        and attempt.provider_attempts >= maximum_provider_requests
                    ):
                        attempt.status = "FAILED_FINAL"
                        attempt.failure_code = "provider_retry_limit_reached"
                        session.commit()
                        raise _failure_from_attempt(attempt)
                    raise AppError(
                        status.HTTP_409_CONFLICT,
                        "ai_turn_in_progress",
                        "This tutor turn is already being processed.",
                        retryable=True,
                    )
            else:
                attempt = attempts.create(
                    conversation_id=conversation.id,
                    learner_id=principal.learner.id,
                    idempotency_key=turn_key,
                    learner_text=learner_message,
                    commit=False,
                )
            provider_call = usage.reserve_provider_call(
                learner_id=principal.learner.id,
                user_id=principal.user.id,
                operation_kind="llm",
                attempt_reference=attempt.id,
            )
            provider_call_id = provider_call.id
            session.commit()
            session.refresh(attempt)
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
    if content_response is None:
        try:
            reexplanation = correction_reexplanation_input(
                previous_result,
                in_english=language_decision.language == ExplanationLanguage.ENGLISH,
            ) if language_decision.state != ExplanationLanguageState.DEFAULT_PREFERENCE else None
            if learner_intent in {LearnerIntent.EXPLANATION, LearnerIntent.LANGUAGE_CHANGE}:
                learner_input = reexplanation or learner_message
            elif learner_intent == LearnerIntent.RETRY:
                learner_input = tutor_input_for_retry(learner_message, previous_result)
            elif learner_intent == LearnerIntent.GUIDED_ROLEPLAY:
                learner_input = (
                    f"The learner requested a guided, interactive scenario lesson: {learner_message}\n\n"
                    "Leave any older correction loop. Set the requested scene, teach at most two short useful "
                    "English phrases step by step with natural Telugu support when requested, then ask the learner "
                    "to say the next phrase so the roleplay continues interactively. Do not invent a grammar error."
                )
            else:
                learner_input = learner_message
            if not (
                language_decision.state == ExplanationLanguageState.DEFAULT_PREFERENCE
                and language_decision.effective_mode == LanguageMode.ENGLISH
            ):
                learner_input = f"{learner_input}\n\n{explanation_policy_instruction(language_decision)}"
            content_response = AIConversationService(provider).generate(AIConversationRequest(
                learner_id=principal.learner.id,
                conversation_id=conversation.id,
                learner_level=principal.learner.proficiency_level,
                preferred_language=language_decision.effective_mode.value,
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
                    for item in conversation.messages
                    if not _unexpected_foreign_script(item.learner_text)
                ][-3:],
                current_learner_message=_tutor_input(
                    learner_input,
                    input_source=data.input_source,
                    stt_confidence=data.stt_confidence,
                ),
                correlation_id=request.state.correlation_id,
            ))
            content_response = apply_pedagogy_guardrails(
                protect_learner_facts(content_response, learner_message)
            )
            content_response = enforce_response_output_safety(
                content_response,
                language_decision.effective_mode,
            )
        except ProviderError as exc:
            record_stage_timing(
                request,
                "llm",
                (perf_counter() - started_at) * 1000,
            )
            session.rollback()
            attempt = attempts.get(conversation.id, turn_key)
            if attempt is None:
                raise AppError(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "ai_turn_state_lost",
                    "The tutor turn could not be recovered. Send it again.",
                    retryable=False,
                ) from exc
            if provider_call_id is not None:
                _reconcile_provider_call(
                    usage,
                    provider_call_id,
                    request_count=exc.provider_requests,
                    input_units=exc.input_units,
                    output_units=exc.output_units,
                    outcome="FAILURE",
                    failed=True,
                )
            attempts.mark_provider_failure(
                attempt,
                exc,
                maximum_provider_requests=maximum_provider_requests,
            )
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
                "provider_requests=%s retryable=%s schema_path=%s",
                request.state.request_id,
                attempt.id,
                exc.failure_code,
                exc.provider_requests,
                exc.retryable,
                exc.schema_path or "none",
            )
            request.app.state.metrics.increment(
                "ai_provider_timeouts"
                if isinstance(exc, ProviderTimeout)
                else "ai_provider_failures"
            )
            if attempt.status == "FAILED_FINAL" and exc.retryable:
                raise _failure_from_attempt(attempt) from exc
            raise _provider_app_error(exc) from exc
        if provider_call_id is not None:
            _reconcile_provider_call(
                usage,
                provider_call_id,
                request_count=content_response.usage.provider_requests,
                input_units=content_response.usage.input_units,
                output_units=content_response.usage.output_units,
            )
        provider_latency_ms = (perf_counter() - started_at) * 1000
        record_stage_timing(request, "llm", provider_latency_ms)
        attempts.checkpoint_provider_success(
            attempt,
            content_response,
            provider_latency_ms=provider_latency_ms,
        )

    if response is None or review_result is None:
        review_uses_provider = (
            language_decision.effective_mode != LanguageMode.ENGLISH
            and request.app.state.language_review_provider is not None
        )
        if review_uses_provider:
            RuntimeEntitlementService(
                session,
                request.app.state.commercial_service.config,
            ).enforce_provider_budget(principal.learner.id)
        if not attempts.claim_review(attempt, commit=False):
            session.rollback()
            raise AppError(
                status.HTTP_409_CONFLICT,
                "ai_turn_in_progress",
                "This tutor turn is already being reviewed.",
                retryable=True,
            )
        review_call_id = None
        if review_uses_provider:
            review_call = usage.reserve_provider_call(
                learner_id=principal.learner.id,
                user_id=principal.user.id,
                operation_kind="language_review",
                attempt_reference=attempt.id,
            )
            review_call_id = review_call.id
        session.commit()
        session.refresh(attempt)
        review_started_at = perf_counter()
        try:
            language_mode = language_decision.effective_mode
            response, review_result = LanguageReviewService(
                request.app.state.language_review_provider
            ).review(
                content_response,
                language_mode=language_mode,
                learning_objective=SCENARIOS_BY_ID[conversation.scenario_id].name,
                learner_level=principal.learner.proficiency_level,
                correlation_id=request.state.correlation_id,
            )
        except ProviderError as exc:
            review_latency_ms = (perf_counter() - review_started_at) * 1000
            record_stage_timing(request, "review", review_latency_ms)
            session.rollback()
            attempt = attempts.get(conversation.id, turn_key)
            if attempt is None:
                raise AppError(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "ai_turn_state_lost",
                    "The tutor turn could not be recovered. Send it again.",
                    retryable=False,
                ) from exc
            language_mode = language_decision.effective_mode
            response = content_response
            review_result = degraded_review_result(
                content_response,
                language_mode=language_mode,
                learning_objective=SCENARIOS_BY_ID[conversation.scenario_id].name,
                learner_level=principal.learner.proficiency_level,
                correlation_id=request.state.correlation_id,
                failure_code=exc.failure_code,
            )
            if review_call_id is not None:
                _reconcile_provider_call(
                    usage,
                    review_call_id,
                    request_count=exc.provider_requests,
                    input_units=exc.input_units,
                    output_units=exc.output_units,
                    outcome="FAILURE",
                    failed=True,
                )
            attempts.checkpoint_review_degraded(
                attempt,
                response,
                review_result,
                exc,
                review_latency_ms=review_latency_ms,
            )
            usage.record(
                ai_turn_attempt_id=attempt.id,
                learner_id=principal.learner.id,
                user_id=principal.user.id,
                provider_kind="language_review",
                outcome="DEGRADED",
                request_count=exc.provider_requests,
                retries=max(0, exc.provider_requests - 1),
                input_units=exc.input_units,
                output_units=exc.output_units,
                failed=True,
                degraded=True,
                commit=False,
            )
            session.commit()
            logger.warning(
                "language_review_degraded request_id=%s attempt_id=%s failure_code=%s "
                "provider_requests=%s retryable=%s schema_path=%s",
                request.state.request_id,
                attempt.id,
                exc.failure_code,
                exc.provider_requests,
                exc.retryable,
                exc.schema_path or "none",
            )
            request.app.state.metrics.increment("language_review_failures")
        else:
            review_latency_ms = (perf_counter() - review_started_at) * 1000
            record_stage_timing(request, "review", review_latency_ms)
            if review_call_id is not None:
                _reconcile_provider_call(
                    usage,
                    review_call_id,
                    request_count=review_result.usage.provider_requests,
                    input_units=review_result.usage.input_units,
                    output_units=review_result.usage.output_units,
                )
            attempts.checkpoint_review_success(
                attempt,
                response,
                review_result,
                review_latency_ms=review_latency_ms,
            )
            logger.info(
                "language_review_completed request_id=%s attempt_id=%s mode=%s changed=%s "
                "reason=%s expression=%s provider_requests=%s",
                request.state.request_id,
                attempt.id,
                review_result.language_mode,
                review_result.review_changed,
                review_result.review_reason_code,
                review_result.expression_hint,
                review_result.usage.provider_requests,
            )
            request.app.state.metrics.increment("language_review_requests")

    response = apply_pedagogy_guardrails(protect_learner_facts(response, learner_message))
    try:
        response = enforce_response_output_safety(
            response,
            language_decision.effective_mode,
        )
    except ProviderOutputInvalid as exc:
        raise _provider_app_error(exc) from exc
    latency_ms = float(
        attempt.result_json.get("provider_latency_ms", (perf_counter() - started_at) * 1000)
    ) + float(attempt.result_json.get("review_latency_ms", 0))
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
    coaching = build_coaching_outcome(
        response,
        learner_level=principal.learner.proficiency_level,
        language_mode=language_decision.effective_mode,
        previous_result=previous_result,
        previous_turn_id=(
            str((previous_result or {}).get("retry_of_turn_id") or previous_attempt.id)
            if previous_attempt is not None else None
        ),
        learner_text=learner_message,
        explanation_language_state=language_decision.state,
        learner_intent=learner_intent,
    )
    response = coaching.response
    try:
        response = enforce_response_output_safety(
            response,
            language_decision.effective_mode,
        )
    except ProviderOutputInvalid as exc:
        raise _provider_app_error(exc) from exc
    result = _api_result(
        response, policy, attempt.id, review_result, coaching, language_decision, previous_result, learner_intent,
    )
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
            learner_message,
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
            return _completed_api_result(recovered, default_language_mode)
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


def _tts_app_error(exc: ProviderError) -> AppError:
    if isinstance(exc, ProviderTimeout):
        return AppError(status.HTTP_504_GATEWAY_TIMEOUT, "tts_timeout", "Tutor voice timed out. Try audio again.", retryable=True)
    if isinstance(exc, ProviderRateLimited):
        return AppError(status.HTTP_429_TOO_MANY_REQUESTS, "tts_rate_limited", "Tutor voice is busy. Wait, then try again.", retryable=True)
    if isinstance(exc, ProviderConnectionError):
        return AppError(status.HTTP_503_SERVICE_UNAVAILABLE, "tts_connection_error", "Tutor voice could not connect. Try again.", retryable=True)
    if isinstance(exc, ProviderServiceError):
        return AppError(status.HTTP_502_BAD_GATEWAY, "tts_provider_error", "Tutor voice had a temporary provider error.", retryable=True)
    if isinstance(exc, ProviderMalformedResponse):
        return AppError(status.HTTP_502_BAD_GATEWAY, "tts_invalid_audio", "Tutor voice returned invalid audio.", retryable=False)
    return AppError(status.HTTP_503_SERVICE_UNAVAILABLE, "tts_unavailable", "Tutor voice is unavailable.", retryable=False)


@router.post("/conversations/{conversation_id}/ai-turns/{turn_id}/speech")
def synthesize_tutor_speech(
    conversation_id: str,
    turn_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    """Return the exact completed tutor turn as provider-generated audio."""
    logger.info(
        "tts_request_received request_id=%s provider=%s",
        request.state.request_id,
        request.app.state.settings.text_to_speech_provider,
    )
    enforce_rate_limit(request, "voice_turn", principal.user.id)
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "conversation_not_found", "Conversation not found.")
    ensure_owner(conversation.learner_id, principal)
    ai_attempt = session.get(AITurnAttempt, turn_id)
    if (
        ai_attempt is None
        or ai_attempt.conversation_id != conversation.id
        or ai_attempt.learner_id != principal.learner.id
        or ai_attempt.status != "COMPLETED"
    ):
        raise AppError(status.HTTP_404_NOT_FOUND, "tutor_turn_not_found", "Completed tutor turn not found.")
    ai_attempt_id = str(ai_attempt.id)

    api_result = ai_attempt.result_json.get("api_result", {})
    spoken_text = str(api_result.get("spoken_text") or "").strip()
    if not spoken_text:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "tts_empty_text", "This tutor turn has no speech text.")
    language_mode = LanguageMode(str(api_result.get("language_mode") or "ENGLISH"))
    try:
        spoken_text = normalize_spoken_output(spoken_text, language_mode)
    except ProviderOutputInvalid as exc:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "tts_invalid_text",
            "This tutor turn contains invalid speech text.",
            retryable=False,
        ) from exc

    tutor = get_tutor(principal.learner.preferred_tutor_id or "ananya")
    settings = request.app.state.settings
    voice = settings.openai_tts_ananya_voice if tutor.tutor_id == "ananya" else settings.openai_tts_arjun_voice
    tone = "warm, patient, and professional" if tutor.tutor_id == "ananya" else "friendly and confident"
    if language_mode == LanguageMode.TELUGU_DOMINANT:
        instructions = (
            f"Speak at a moderate teaching pace in natural contemporary Andhra/Telangana Telugu with a {tone} tone. "
            "Use conversational Telugu-English code switching. Give embedded English examples in clear neutral "
            "Indian English; avoid strong American or British intonation. Do not anglicize Telugu."
        )
    elif language_mode == LanguageMode.ENGLISH_TELUGU:
        instructions = (
            f"Speak at a moderate teaching pace with a {tone} Indian teacher tone. Use native conversational "
            "Andhra/Telangana Telugu rhythm for Telugu. Give corrected English sentences and grammar terms in "
            "clear neutral Indian English; switch languages smoothly and avoid strong American or British intonation."
        )
    else:
        instructions = (
            f"Speak in clear neutral Indian English with a {tone} teacher tone at a moderate pace. "
            "Avoid strong American or British intonation. Pronounce every word clearly and preserve the written meaning."
        )
    provider = request.app.state.text_to_speech_provider
    if provider is None:
        raise AppError(status.HTTP_503_SERVICE_UNAVAILABLE, "tts_unavailable", "Tutor voice is unavailable.", retryable=True)

    spoken_hash = hashlib.sha256(spoken_text.encode()).hexdigest()
    repository = TTSSynthesisRepository(session)
    usage = UsageService(session)
    provider_call_id = None
    attempt = repository.get(ai_attempt.id)
    if attempt is not None:
        if attempt.learner_id != principal.learner.id or attempt.spoken_text_hash != spoken_hash:
            raise AppError(status.HTTP_409_CONFLICT, "tts_turn_conflict", "Tutor voice identity conflict.", retryable=False)
        _recover_stale_provider_claim(
            session,
            attempt,
            transitions={"IN_PROGRESS": "RETRYABLE_FAILURE"},
            maximum_provider_requests=UsageLimits().maximum_provider_retries + 1,
        )
        if attempt.status == "SUCCEEDED" and attempt.audio_bytes and attempt.content_type:
            return _speech_response(attempt, cache_status="HIT")
        if attempt.status == "IN_PROGRESS":
            raise AppError(status.HTTP_409_CONFLICT, "tts_in_progress", "Tutor voice is already being generated.", retryable=True)
        if attempt.status == "FAILED_FINAL":
            if attempt.failure_code == "provider_retry_limit_reached":
                raise AppError(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "tts_retry_limit_reached",
                    "Tutor voice could not recover after the allowed retries.",
                    retryable=False,
                )
            raise AppError(status.HTTP_502_BAD_GATEWAY, "tts_invalid_audio", "Tutor voice could not produce valid audio.", retryable=False)
        RuntimeEntitlementService(
            session,
            request.app.state.commercial_service.config,
        ).enforce_provider_budget(principal.learner.id)
        maximum_provider_requests = UsageLimits().maximum_provider_retries + 1
        if attempt.provider_requests >= maximum_provider_requests:
            attempt.status = "FAILED_FINAL"
            attempt.failure_code = "provider_retry_limit_reached"
            session.commit()
            raise AppError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "tts_retry_limit_reached",
                "Tutor voice could not recover after the allowed retries.",
                retryable=False,
            )
        if not repository.claim_retry(
            attempt,
            maximum_provider_requests=maximum_provider_requests,
            commit=False,
        ):
            session.rollback()
            raise AppError(
                status.HTTP_409_CONFLICT,
                "tts_in_progress",
                "Tutor voice is already being generated.",
                retryable=True,
            )
        provider_call = usage.reserve_provider_call(
            learner_id=principal.learner.id,
            user_id=principal.user.id,
            operation_kind="tts",
            attempt_reference=attempt.id,
        )
        provider_call_id = provider_call.id
        session.commit()
        session.refresh(attempt)
    else:
        RuntimeEntitlementService(
            session,
            request.app.state.commercial_service.config,
        ).enforce_provider_budget(principal.learner.id)
        try:
            attempt = repository.create(
                ai_turn_attempt_id=ai_attempt.id,
                learner_id=principal.learner.id,
                tutor_id=tutor.tutor_id,
                provider="openai" if settings.text_to_speech_provider == "openai" else "test-only-fake",
                model=settings.openai_tts_model if settings.text_to_speech_provider == "openai" else "deterministic-tts",
                voice=voice,
                spoken_text_hash=spoken_hash,
                input_characters=len(spoken_text),
                commit=False,
            )
            provider_call = usage.reserve_provider_call(
                learner_id=principal.learner.id,
                user_id=principal.user.id,
                operation_kind="tts",
                attempt_reference=attempt.id,
            )
            provider_call_id = provider_call.id
            session.commit()
            session.refresh(attempt)
        except IntegrityError as exc:
            session.rollback()
            raise AppError(status.HTTP_409_CONFLICT, "tts_in_progress", "Tutor voice is already being generated.", retryable=True) from exc

    tts_started_at = perf_counter()
    try:
        result = provider.synthesize(TextToSpeechRequest(
            text=spoken_text,
            language="te-IN" if language_mode != LanguageMode.ENGLISH else "en-IN",
            voice_reference=voice,
            speaking_rate=settings.openai_tts_speed,
            instructions=instructions,
            learner_level=principal.learner.proficiency_level,
            correlation_id=request.state.correlation_id,
        ))
    except ProviderError as exc:
        record_stage_timing(request, "tts", (perf_counter() - tts_started_at) * 1000)
        session.rollback()
        attempt = repository.get(ai_attempt_id)
        if attempt is None:
            raise AppError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "tts_state_lost",
                "Tutor voice could not be recovered. Try again.",
                retryable=True,
            ) from exc
        repository.fail(attempt, exc.failure_code, exc.provider_requests, commit=False)
        if provider_call_id is not None:
            _reconcile_provider_call(
                usage,
                provider_call_id,
                request_count=exc.provider_requests,
                input_units=len(spoken_text),
                outcome="FAILURE",
                failed=True,
            )
        usage.record(
            learner_id=principal.learner.id,
            user_id=principal.user.id,
            provider_kind="tts",
            voice_session_id=conversation.id,
            outcome="FAILURE",
            request_count=max(1, exc.provider_requests),
            input_units=len(spoken_text),
            failed=True,
            commit=False,
        )
        retry_limit_reached = attempt.provider_requests >= UsageLimits().maximum_provider_retries + 1
        if not exc.retryable or retry_limit_reached:
            attempt.status = "FAILED_FINAL"
        if retry_limit_reached and exc.retryable:
            attempt.failure_code = "provider_retry_limit_reached"
        session.commit()
        logger.warning(
            "tts_provider_failure request_id=%s attempt_id=%s failure_code=%s retryable=%s",
            request.state.request_id, attempt.id, exc.failure_code, exc.retryable,
        )
        request.app.state.metrics.increment("tts_provider_failures")
        if retry_limit_reached and exc.retryable:
            raise AppError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "tts_retry_limit_reached",
                "Tutor voice could not recover after the allowed retries.",
                retryable=False,
            ) from exc
        raise _tts_app_error(exc) from exc

    record_stage_timing(request, "tts", (perf_counter() - tts_started_at) * 1000)
    if provider_call_id is not None:
        _reconcile_provider_call(
            usage,
            provider_call_id,
            request_count=result.provider_requests,
            input_units=len(spoken_text),
        )
    repository.succeed(attempt, result, commit=False)
    usage.record(
        learner_id=principal.learner.id,
        user_id=principal.user.id,
        provider_kind="tts",
        voice_session_id=conversation.id,
        request_count=max(1, result.provider_requests),
        input_units=len(spoken_text),
        commit=False,
    )
    session.commit()
    request.app.state.metrics.increment("tts_requests")
    request.app.state.metrics.observe("tts_audio_size_bytes", len(result.audio_bytes))
    logger.info(
        "tts_generation_completed request_id=%s attempt_id=%s model=%s voice=%s bytes=%s provider_requests=%s",
        request.state.request_id, attempt.id, attempt.model_used, attempt.voice_used,
        attempt.audio_size_bytes, attempt.provider_requests,
    )
    return _speech_response(attempt, cache_status="MISS")


def _speech_response(attempt, *, cache_status: str) -> Response:
    return Response(
        content=attempt.audio_bytes,
        media_type=attempt.content_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "Content-Disposition": "inline; filename=tutor-speech.mp3",
            "X-Content-Type-Options": "nosniff",
            "X-TTS-Attempt-ID": attempt.id,
            "X-TTS-Provider": attempt.provider,
            "X-TTS-Model": attempt.model_used,
            "X-TTS-Voice": attempt.voice_used,
            "X-TTS-Cache": cache_status,
            "X-TTS-Input-Characters": str(attempt.input_characters),
            "X-TTS-Provider-Requests": str(attempt.provider_requests),
            "X-TTS-Usage-Classification": attempt.usage_classification,
        },
    )


@router.post("/conversations/{conversation_id}/transcriptions", response_model=VoiceTranscriptionRead)
async def transcribe_voice_input(
    conversation_id: str,
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

    turn_key = idempotency_key or request.state.request_id
    audio_digest = hashlib.sha256(audio).hexdigest()
    attempt = session.scalar(select(VoiceTranscriptionAttempt).where(
        VoiceTranscriptionAttempt.conversation_id == conversation.id,
        VoiceTranscriptionAttempt.idempotency_key == turn_key,
    ))
    if attempt is not None:
        _ensure_transcription_identity(
            attempt,
            learner_id=principal.learner.id,
            audio_digest=audio_digest,
            content_type=content_type,
        )
        _recover_stale_provider_claim(
            session,
            attempt,
            transitions={"IN_PROGRESS": "FAILED_RETRYABLE"},
            maximum_provider_requests=UsageLimits().maximum_provider_retries + 1,
        )
        completed = _transcription_attempt_outcome(attempt)
        if completed is not None:
            return completed

    entitlements = RuntimeEntitlementService(
        session,
        request.app.state.commercial_service.config,
    )
    try:
        entitlements.enforce_voice(principal.learner.id, _TRANSCRIPTION_RESERVATION_MS)
        entitlements.enforce_provider_budget(principal.learner.id)
    except AppError:
        # A request can finish while this request waits for the learner quota lock.
        # Preserve idempotent replay even when no fresh allowance remains.
        session.rollback()
        latest = session.scalar(select(VoiceTranscriptionAttempt).where(
            VoiceTranscriptionAttempt.conversation_id == conversation.id,
            VoiceTranscriptionAttempt.idempotency_key == turn_key,
        ))
        if latest is not None:
            _ensure_transcription_identity(
                latest,
                learner_id=principal.learner.id,
                audio_digest=audio_digest,
                content_type=content_type,
            )
            completed = _transcription_attempt_outcome(latest)
            if completed is not None:
                return completed
        raise

    # Re-read after taking the learner quota lock so concurrent requests with
    # the same identity cannot create or retry duplicate provider work.
    locked_attempt = session.scalar(select(VoiceTranscriptionAttempt).where(
        VoiceTranscriptionAttempt.conversation_id == conversation.id,
        VoiceTranscriptionAttempt.idempotency_key == turn_key,
    ).execution_options(populate_existing=True))
    maximum_provider_requests = UsageLimits().maximum_provider_retries + 1
    if locked_attempt is not None:
        _ensure_transcription_identity(
            locked_attempt,
            learner_id=principal.learner.id,
            audio_digest=audio_digest,
            content_type=content_type,
        )
        completed = _transcription_attempt_outcome(locked_attempt)
        if completed is not None:
            session.rollback()
            return completed
        claimed = cast(CursorResult[Any], session.execute(
            update(VoiceTranscriptionAttempt)
            .where(
                VoiceTranscriptionAttempt.id == locked_attempt.id,
                VoiceTranscriptionAttempt.status == "FAILED_RETRYABLE",
                VoiceTranscriptionAttempt.provider_requests < maximum_provider_requests,
            )
            .values(
                status="IN_PROGRESS",
                failure_code=None,
                charge_duration_ms=(
                    VoiceTranscriptionAttempt.charge_duration_ms
                    + _TRANSCRIPTION_RESERVATION_MS
                ),
                provider_requests=VoiceTranscriptionAttempt.provider_requests + 1,
                updated_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session=False)
        )).rowcount == 1
        if not claimed:
            session.rollback()
            latest = session.scalar(select(VoiceTranscriptionAttempt).where(
                VoiceTranscriptionAttempt.id == locked_attempt.id
            ).execution_options(populate_existing=True))
            if latest is not None:
                completed = _transcription_attempt_outcome(latest)
                if completed is not None:
                    return completed
            raise AppError(
                status.HTTP_409_CONFLICT,
                "speech_to_text_in_progress",
                "This voice capture is already being transcribed.",
                retryable=True,
            )
        session.flush()
        session.refresh(locked_attempt)
        attempt = locked_attempt
    else:
        attempt = VoiceTranscriptionAttempt(
            conversation_id=conversation.id,
            learner_id=principal.learner.id,
            idempotency_key=turn_key,
            audio_digest=audio_digest,
            content_type=content_type,
            status="IN_PROGRESS",
            charge_duration_ms=_TRANSCRIPTION_RESERVATION_MS,
            provider_requests=1,
            result_json={},
        )
        session.add(attempt)
        session.flush()
    usage = UsageService(session)
    provider_call = usage.reserve_provider_call(
        learner_id=principal.learner.id,
        user_id=principal.user.id,
        operation_kind="stt",
        attempt_reference=attempt.id,
        duration_ms=_TRANSCRIPTION_RESERVATION_MS,
    )
    attempt_id = str(attempt.id)
    provider_call_id = provider_call.id
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(
            status.HTTP_409_CONFLICT,
            "speech_to_text_in_progress",
            "This voice capture is already being transcribed.",
            retryable=True,
        ) from exc

    extension = {
        "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a",
        "audio/wav": "wav", "audio/mpeg": "mp3",
    }[content_type]
    expected_language = "te" if _expects_telugu(principal.learner) else None
    stt_request = SpeechToTextRequest(
        audio_asset_reference=f"ephemeral/{request.state.request_id}.{extension}",
        audio_bytes=audio,
        filename=f"speech.{extension}",
        content_type=content_type,
        language_hint=expected_language or "en",
        learner_id=principal.learner.id,
        voice_session_id=conversation.id,
        voice_turn_id=turn_key,
        correlation_id=request.state.correlation_id,
        maximum_duration_seconds=60,
        duration_seconds=duration_ms / 1000,
        size_bytes=len(audio),
    )
    stt_started_at = perf_counter()
    try:
        result = await run_in_threadpool(provider.transcribe, stt_request)
    except ValueError as exc:
        rejected_provider_requests = max(
            1,
            int(getattr(exc, "provider_requests", 1)),
        )
        _reconcile_provider_call(
            usage,
            provider_call_id,
            request_count=rejected_provider_requests,
            duration_ms=_TRANSCRIPTION_RESERVATION_MS,
            outcome="REJECTED",
            failed=True,
        )
        attempt.provider_requests += max(0, rejected_provider_requests - 1)
        attempt.status = "REJECTED_FINAL"
        attempt.failure_code = "no_speech_detected"
        attempt.completed_at = datetime.now(UTC)
        attempt.updated_at = attempt.completed_at
        session.commit()
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "no_speech_detected",
            "No clear speech was detected.",
        ) from exc
    except ProviderTimeout as exc:
        session.rollback()
        attempt = session.get(VoiceTranscriptionAttempt, attempt_id)
        if attempt is None:
            raise RuntimeError("Voice transcription attempt disappeared during timeout recovery") from exc
        _reconcile_provider_call(
            usage,
            provider_call_id,
            request_count=exc.provider_requests,
            duration_ms=_TRANSCRIPTION_RESERVATION_MS,
            outcome="FAILURE",
            failed=True,
        )
        attempt.provider_requests += max(0, exc.provider_requests - 1)
        attempt.failure_code = "speech_to_text_timeout"
        attempt.status = (
            "FAILED_RETRYABLE"
            if attempt.provider_requests < UsageLimits().maximum_provider_retries + 1
            else "FAILED_FINAL"
        )
        attempt.updated_at = datetime.now(UTC)
        session.commit()
        if attempt.status == "FAILED_FINAL":
            raise AppError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "speech_to_text_retry_limit_reached",
                "Speech recognition could not recover after the allowed retries.",
                retryable=False,
            ) from exc
        raise AppError(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "speech_to_text_timeout",
            "Speech recognition timed out.",
            retryable=True,
        ) from exc
    except ProviderUnavailable as exc:
        session.rollback()
        attempt = session.get(VoiceTranscriptionAttempt, attempt_id)
        if attempt is None:
            raise RuntimeError("Voice transcription attempt disappeared during unavailable recovery") from exc
        _reconcile_provider_call(
            usage,
            provider_call_id,
            request_count=exc.provider_requests,
            duration_ms=_TRANSCRIPTION_RESERVATION_MS,
            outcome="FAILURE",
            failed=True,
        )
        attempt.provider_requests += max(0, exc.provider_requests - 1)
        attempt.failure_code = "speech_to_text_unavailable"
        attempt.status = (
            "FAILED_RETRYABLE"
            if attempt.provider_requests < UsageLimits().maximum_provider_retries + 1
            else "FAILED_FINAL"
        )
        attempt.updated_at = datetime.now(UTC)
        session.commit()
        if attempt.status == "FAILED_FINAL":
            raise AppError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "speech_to_text_retry_limit_reached",
                "Speech recognition could not recover after the allowed retries.",
                retryable=False,
            ) from exc
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "speech_to_text_unavailable",
            "Speech recognition is unavailable.",
            retryable=True,
        ) from exc
    finally:
        record_stage_timing(request, "stt", (perf_counter() - stt_started_at) * 1000)

    actual_duration_ms = _authoritative_duration_ms(result.duration_seconds)
    attempt.charge_duration_ms = max(
        0,
        attempt.charge_duration_ms - _TRANSCRIPTION_RESERVATION_MS,
    ) + actual_duration_ms
    try:
        if result.confidence is not None and result.confidence < 0.2:
            raise UnusableTranscript("Speech confidence is too low.")
        expected_language = "te" if _expects_telugu(principal.learner, result.detected_language) else None
        transcript = safe_transcript(result.transcript, expected_language=expected_language)
    except UnusableTranscript as exc:
        _reconcile_provider_call(
            usage,
            provider_call_id,
            request_count=result.provider_requests,
            duration_ms=actual_duration_ms,
            input_units=actual_duration_ms,
            output_units=len(result.transcript),
            outcome="REJECTED",
            failed=True,
        )
        attempt.status = "REJECTED_FINAL"
        attempt.failure_code = "no_speech_detected"
        attempt.completed_at = datetime.now(UTC)
        attempt.updated_at = attempt.completed_at
        session.commit()
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "no_speech_detected",
            "No clear speech was detected.",
        ) from exc
    result_json = {
        "transcript": transcript,
        "detected_language": result.detected_language,
        "confidence": result.confidence,
        "duration_ms": actual_duration_ms,
        "size_bytes": len(audio),
    }
    attempt.provider_requests += max(0, result.provider_requests - 1)
    attempt.status = "COMPLETED"
    attempt.failure_code = None
    attempt.result_json = result_json
    attempt.completed_at = datetime.now(UTC)
    attempt.updated_at = attempt.completed_at
    _reconcile_provider_call(
        usage,
        provider_call_id,
        request_count=result.provider_requests,
        duration_ms=actual_duration_ms,
        input_units=actual_duration_ms,
        output_units=len(transcript),
    )
    usage.record(
        learner_id=principal.learner.id,
        user_id=principal.user.id,
        provider_kind="stt",
        voice_session_id=conversation.id,
        input_units=actual_duration_ms,
        output_units=len(transcript),
        request_count=max(1, result.provider_requests),
        commit=False,
    )
    session.commit()
    request.app.state.metrics.increment("voice_transcriptions_completed")
    request.app.state.metrics.observe("voice_capture_size_bytes", len(audio))
    return result_json


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
        commercial_config=request.app.state.commercial_service.config,
    )
    return service.process(
        session_id=session_id, turn_id=turn_id, learner=principal.learner, user=principal.user,
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
