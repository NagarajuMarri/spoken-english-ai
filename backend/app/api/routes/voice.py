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

router = APIRouter(prefix="/api/v1", tags=["voice"])


def service(request: Request, session: Session) -> VoiceService:
    return VoiceService(session, request.app.state.settings.temporary_audio_expiration_hours)


def session_payload(item):
    return {
        "id": item.id, "learner_id": item.learner_id, "scenario_id": item.scenario_id,
        "status": item.status, "created_at": item.created_at, "completed_at": item.completed_at,
        "turns": item.turns, "audio_assets": item.assets,
    }


@router.get("/learners/{learner_id}/voice-consent", response_model=VoiceConsentRead)
def get_consent(learner_id: str, request: Request, session: Session = Depends(get_db)):
    return service(request, session).consent(learner_id)


@router.put("/learners/{learner_id}/voice-consent", response_model=VoiceConsentRead)
def put_consent(learner_id: str, data: VoiceConsentUpdate, request: Request, session: Session = Depends(get_db)):
    return service(request, session).update_consent(learner_id, data)


@router.delete("/learners/{learner_id}/voice-consent", response_model=VoiceConsentRead)
def delete_consent(learner_id: str, request: Request, session: Session = Depends(get_db)):
    return service(request, session).withdraw(learner_id)


@router.post("/voice-sessions", response_model=VoiceSessionRead, status_code=status.HTTP_201_CREATED)
def create_voice_session(data: VoiceSessionCreate, request: Request, session: Session = Depends(get_db)):
    return session_payload(service(request, session).create_session(data.learner_id, data.scenario_id))


@router.get("/voice-sessions/{session_id}", response_model=VoiceSessionRead)
def get_voice_session(session_id: str, request: Request, session: Session = Depends(get_db)):
    return session_payload(service(request, session).get_session(session_id))


@router.post("/voice-sessions/{session_id}/turns", response_model=VoiceTurnRead)
def add_voice_turn(session_id: str, data: VoiceTurnCreate, request: Request, session: Session = Depends(get_db)):
    turn, assessment = service(request, session).add_turn(session_id, data)
    return {**turn.__dict__, "pronunciation_assessment": asdict(assessment)}


@router.post("/voice-sessions/{session_id}/complete", response_model=VoiceSessionRead)
def complete_voice_session(session_id: str, request: Request, session: Session = Depends(get_db)):
    return session_payload(service(request, session).complete(session_id))


@router.get("/learners/{learner_id}/daily-plan", response_model=DailyPlanRead)
def daily_plan(learner_id: str, request: Request, session: Session = Depends(get_db)):
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
