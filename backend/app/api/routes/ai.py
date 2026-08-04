from time import perf_counter

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.ai.models import AIConversationRequest
from backend.app.ai.service import AIConversationService, AdaptivePolicy
from backend.app.conversation_memory.models import MemorySignalInput
from backend.app.conversation_memory.service import ConversationMemoryService
from backend.app.core.errors import AppError
from backend.app.core.operations import enforce_rate_limit
from backend.app.core.security import Principal, current_principal, ensure_owner
from backend.app.db.session import get_db
from backend.app.domain.scenarios import SCENARIOS_BY_ID
from backend.app.models import Conversation, VoiceProcessingAttempt
from backend.app.intelligent_learning.models import CostEvent, LearnerSummary, PromptContext
from backend.app.providers.pronunciation.deterministic import DeterministicPronunciationProvider
from backend.app.providers.stt.deterministic import DeterministicSpeechToTextProvider
from backend.app.providers.tts.deterministic import DeterministicTextToSpeechProvider
from backend.app.repositories.conversations import ConversationRepository
from backend.app.usage.service import UsageService
from backend.app.voice.models import VoiceTutorResult
from backend.app.voice.orchestration import VoiceTutorOrchestrationService
from backend.app.tutors import get_tutor

router = APIRouter(prefix="/api/v1", tags=["ai-tutor"])


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


class VoiceProcessRequest(BaseModel):
    generate_audio: bool = True


@router.post("/conversations/{conversation_id}/ai-turns", response_model=AITurnRead)
def ai_turn(
    conversation_id: str,
    data: AITurnCreate,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    enforce_rate_limit(request, "authenticated_burst", principal.user.id)
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "conversation_not_found", "Conversation not found.")
    ensure_owner(conversation.learner_id, principal)
    usage = UsageService(session)
    usage.enforce(principal.learner.id, principal.user.id)
    tutor = get_tutor(principal.learner.preferred_tutor_id or "ananya")
    learning_engine = request.app.state.learning_engine
    category = learning_engine.classifier.classify(data.message)
    route_decision = learning_engine.router.route(category)
    if not route_decision.requires_llm:
        engine_result = learning_engine.handle(
            message=data.message,
            context=PromptContext(
                tutor_persona=tutor.prompt_profile,
                learner_summary=LearnerSummary(current_lesson=conversation.scenario_id),
                current_lesson=conversation.scenario_id,
                current_objective=SCENARIOS_BY_ID[conversation.scenario_id].name,
                recent_conversation=tuple(item.learner_text for item in conversation.messages[-6:]),
            ),
            learner_id=principal.learner.id,
            lesson_id=conversation.scenario_id,
            conversation_id=conversation.id,
        )
        ConversationRepository(session).add_message(conversation.id, data.message, engine_result.response, None)
        request.app.state.metrics.increment("ai_requests_avoided")
        return {
            "tutor_message": engine_result.response,
            "corrected_sentence": None,
            "correction_explanation": None,
            "vocabulary_suggestions": [],
            "next_question": "What would you like to practise next?",
            "encouragement": "Keep going!",
            "adaptive_policy": AdaptivePolicy.decide(
                level=principal.learner.proficiency_level,
                correctness=0.7,
                repeated_mistakes=0,
                confidence=60,
            ).__dict__,
        }
    started_at = perf_counter()
    response = AIConversationService(DeterministicAIProvider()).generate(AIConversationRequest(
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
            item.learner_text for item in conversation.messages[-10:]
        ],
        current_learner_message=data.message,
        correlation_id=request.state.correlation_id,
    ))
    latency_ms = (perf_counter() - started_at) * 1000
    learning_engine.metrics.record(CostEvent(
        learner_id=principal.learner.id,
        lesson_id=conversation.scenario_id,
        conversation_id=conversation.id,
        prompt_tokens=int(response.usage.input_units),
        completion_tokens=int(response.usage.output_units),
        estimated_cost_usd=(response.usage.input_units * 0.00000015 + response.usage.output_units * 0.0000006),
        response_latency_ms=latency_ms,
        cache_hit=False,
        model_used=response.provider_metadata_reference,
    ))
    ConversationRepository(session).add_message(
        conversation.id, data.message, response.tutor_message, response.correction_explanation
    )
    ConversationMemoryService(session).update(principal.learner.id, [
        MemorySignalInput(category="grammar", value=value)
        for value in response.learning_signals.grammar_focus
    ] + [
        MemorySignalInput(category="vocabulary", value=value)
        for value in response.learning_signals.vocabulary
    ])
    usage.record(
        learner_id=principal.learner.id, user_id=principal.user.id,
        provider_kind="llm", input_units=response.usage.input_units,
        output_units=response.usage.output_units,
    )
    policy = AdaptivePolicy.decide(level=principal.learner.proficiency_level, correctness=0.7, repeated_mistakes=1, confidence=60)
    request.app.state.metrics.increment("ai_requests")
    return {
        "tutor_message": response.tutor_message,
        "corrected_sentence": response.corrected_learner_sentence,
        "correction_explanation": response.correction_explanation,
        "vocabulary_suggestions": response.vocabulary_suggestions,
        "next_question": response.conversation_question,
        "encouragement": response.encouragement,
        "adaptive_policy": policy.__dict__,
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
