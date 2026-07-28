from dataclasses import asdict

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.voice import (
    DailyPlanRead,
    VoiceConsentRead,
    VoiceConsentUpdate,
    VoiceSessionCreate,
    VoiceSessionRead,
    VoiceTurnCreate,
    VoiceTurnRead,
)
from backend.app.services.learning import LearningService
from backend.app.services.voice import VoiceService
from backend.app.core.security import Principal, current_principal, ensure_owner, require_learner_owner
from backend.app.core.operations import audit_event, enforce_rate_limit

router = APIRouter(prefix="/api/v1", tags=["voice"])


def service(request: Request, session: Session) -> VoiceService:
    return VoiceService(
        session,
        request.app.state.settings.temporary_audio_expiration_hours,
        request.app.state.metrics,
    )


def session_payload(item):
    return {
        "id": item.id, "learner_id": item.learner_id, "scenario_id": item.scenario_id,
        "status": item.status, "created_at": item.created_at, "completed_at": item.completed_at,
        "turns": item.turns, "audio_assets": item.assets,
    }


@router.get("/learners/{learner_id}/voice-consent", response_model=VoiceConsentRead)
def get_consent(learner_id: str, request: Request, _: Principal = Depends(require_learner_owner), session: Session = Depends(get_db)):
    return service(request, session).consent(learner_id)


@router.put("/learners/{learner_id}/voice-consent", response_model=VoiceConsentRead)
def put_consent(learner_id: str, data: VoiceConsentUpdate, request: Request, _: Principal = Depends(require_learner_owner), session: Session = Depends(get_db)):
    result = service(request, session).update_consent(learner_id, data)
    audit_event(session, "CONSENT_GRANTED" if data.voice_processing_consent else "CONSENT_UPDATED", principal=_)
    return result


@router.delete("/learners/{learner_id}/voice-consent", response_model=VoiceConsentRead)
def delete_consent(learner_id: str, request: Request, _: Principal = Depends(require_learner_owner), session: Session = Depends(get_db)):
    result = service(request, session).withdraw(learner_id)
    audit_event(session, "CONSENT_WITHDRAWN", principal=_)
    return result


@router.post("/voice-sessions", response_model=VoiceSessionRead, status_code=status.HTTP_201_CREATED)
def create_voice_session(data: VoiceSessionCreate, request: Request, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    enforce_rate_limit(request, "authenticated_burst", principal.user.id)
    ensure_owner(data.learner_id, principal)
    result = session_payload(service(request, session).create_session(data.learner_id, data.scenario_id))
    request.app.state.metrics.increment("voice_sessions_started")
    request.app.state.metrics.gauge("active_voice_sessions", 1)
    return result


@router.get("/voice-sessions/{session_id}", response_model=VoiceSessionRead)
def get_voice_session(session_id: str, request: Request, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    item = service(request, session).get_session(session_id)
    ensure_owner(item.learner_id, principal)
    return session_payload(item)


@router.post("/voice-sessions/{session_id}/turns", response_model=VoiceTurnRead)
def add_voice_turn(session_id: str, data: VoiceTurnCreate, request: Request, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    enforce_rate_limit(request, "voice_turn", principal.user.id)
    voice = service(request, session)
    ensure_owner(voice.get_session(session_id).learner_id, principal)
    turn, assessment = voice.add_turn(session_id, data)
    return {**turn.__dict__, "pronunciation_assessment": asdict(assessment)}


@router.post("/voice-sessions/{session_id}/complete", response_model=VoiceSessionRead)
def complete_voice_session(session_id: str, request: Request, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    voice = service(request, session)
    ensure_owner(voice.get_session(session_id).learner_id, principal)
    result = session_payload(voice.complete(session_id))
    request.app.state.metrics.increment("voice_sessions_completed")
    request.app.state.metrics.gauge("active_voice_sessions", 0)
    return result


@router.get("/learners/{learner_id}/daily-plan", response_model=DailyPlanRead)
def daily_plan(learner_id: str, request: Request, _: Principal = Depends(require_learner_owner), session: Session = Depends(get_db)):
    learning = LearningService(session)
    voice = service(request, session)
    lesson = learning.daily_lesson(learner_id)
    streak = learning.streak(learner_id)
    progress = learning.progress(learner_id)
    consent = voice.consent(learner_id)
    return {
        "selected_lesson": {
            "id": lesson.id, "title": lesson.title,
            "proficiency_level": lesson.proficiency_level.value,
        },
        "recommended_scenario": lesson.scenario_id,
        "estimated_minutes": lesson.estimated_duration_minutes,
        "current_streak": streak["current_streak"],
        "recent_progress_summary": progress,
        "voice_availability": consent["active"],
        "consent_required": not consent["active"],
    }
