from datetime import UTC, datetime, timedelta
from pathlib import PurePath

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.core.security import Principal, current_principal
from backend.app.db.session import get_db
from backend.app.models import BetaFeedback, UserAccount
from backend.app.models.entities import AICostMetricEvent, CommercialSubscription, Conversation, ConversationEvaluation, LessonSession, ProgressRecord

router = APIRouter(prefix="/api/v1/launch", tags=["launch-readiness"])


class Feedback(BaseModel):
    rating: int = Field(ge=1, le=5)
    category: str = Field(pattern="^(onboarding|lesson|voice|support|subscription|other)$")
    severity: str = Field(pattern="^(LOW|MEDIUM|HIGH|BLOCKING)$")
    message: str = Field(min_length=3, max_length=1000)
    contact_allowed: bool = False
    screenshot_name: str | None = Field(default=None, max_length=200)


def require_founder(request: Request, principal: Principal) -> None:
    if principal.user.email.lower() not in request.app.state.settings.founders():
        raise AppError(status.HTTP_403_FORBIDDEN, "founder_access_required", "This read-only dashboard is unavailable.")


@router.get("/config")
def launch_config(request: Request):
    settings = request.app.state.settings
    return {"product_name": settings.product_name, "version": settings.release_version, "closed_beta": settings.closed_beta_enabled, "razorpay_mode": settings.razorpay_mode, "payments_enabled": settings.razorpay_enabled, "support_email": settings.support_email, "provider_policy": "OPENAI_FIRST", "release_state": "RELEASE_CANDIDATE_NOT_PUBLIC"}


@router.post("/feedback", status_code=202)
def feedback(data: Feedback, request: Request, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    record = BetaFeedback(learner_id=principal.learner.id, category=data.category, severity=data.severity, message=data.message, contact_allowed=data.contact_allowed, screenshot_name=PurePath(data.screenshot_name).name if data.screenshot_name else None)
    session.add(record); session.commit(); request.app.state.metrics.increment("beta_feedback")
    return {"accepted": True, "feedback_id": record.id, "message": "Thank you. Your feedback was received safely."}


@router.get("/subscription")
def subscription(principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    item = session.scalar(select(CommercialSubscription).where(CommercialSubscription.learner_id == principal.learner.id).order_by(desc(CommercialSubscription.created_at)))
    if item is None:
        return {"plan_id": "FREE", "status": "FREE", "trial_remaining_days": 0, "payment_mode": "test", "entitlements": {"daily_conversations": 5, "voice_minutes": 5}, "fair_use": "Free daily limits apply."}
    remaining = max(0, (item.current_period_end.replace(tzinfo=item.current_period_end.tzinfo or UTC) - datetime.now(UTC)).days)
    return {"plan_id": item.plan_id, "status": item.status, "trial_remaining_days": remaining if item.status == "TRIAL" else 0, "payment_mode": "test", "entitlements": {"daily_conversations": 200 if item.plan_id != "FREE" else 5, "voice_minutes": 120 if item.plan_id != "FREE" else 5}, "fair_use": "Usage is subject to server-side fair-use and cost ceilings."}


@router.post("/subscription/trial", status_code=201)
def start_trial(request: Request, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    if session.scalar(select(CommercialSubscription).where(CommercialSubscription.learner_id == principal.learner.id)) is not None:
        raise AppError(409, "trial_already_used", "A trial or subscription already exists.")
    now = datetime.now(UTC); item = CommercialSubscription(learner_id=principal.learner.id, plan_id="PREMIUM_MONTHLY", status="TRIAL", provider_id="razorpay-test", trial_started_at=now, current_period_end=now + timedelta(days=request.app.state.settings.commercial_trial_days))
    session.add(item); session.commit(); return {"status": "TRIAL", "payment_mode": "test"}


@router.post("/subscription/upgrade", status_code=202)
def request_upgrade(request: Request, principal: Principal = Depends(current_principal)):
    if request.app.state.settings.razorpay_mode != "test":
        raise AppError(503, "payment_mode_unavailable", "Payments are unavailable.")
    return {"status": "PAYMENT_PENDING", "payment_mode": "test", "real_charge": False}


@router.get("/progress")
def progress(principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    learner_id = principal.learner.id; evaluations = list(session.scalars(select(ConversationEvaluation).join(LessonSession).where(LessonSession.learner_id == learner_id)))
    average = lambda name: round(sum(getattr(x, name) for x in evaluations) / len(evaluations), 1) if evaluations else None
    records = list(session.scalars(select(ProgressRecord).where(ProgressRecord.learner_id == learner_id).order_by(desc(ProgressRecord.created_at)).limit(30)))
    conversations = session.scalar(select(func.count()).select_from(Conversation).where(Conversation.learner_id == learner_id)) or 0
    return {"scores": {"grammar": average("grammar_score"), "vocabulary": average("vocabulary_score"), "pronunciation": None, "confidence": average("confidence_score"), "fluency": average("fluency_score")}, "completed_lessons": len(records), "daily_streak": 0, "weekly_activity": sum(x.created_at >= datetime.now(UTC) - timedelta(days=7) for x in records), "monthly_activity": len(records), "learning_goal": principal.learner.learning_goal, "recent_achievements": [], "conversation_history_summary": {"conversations": conversations, "recent_sessions": len(records[:5])}}


@router.get("/founder-dashboard")
def founder_dashboard(request: Request, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    require_founder(request, principal); users = session.scalar(select(func.count()).select_from(UserAccount)) or 0
    registrations = list(session.scalars(select(UserAccount).order_by(desc(UserAccount.created_at)).limit(10))); feedback_items = list(session.scalars(select(BetaFeedback).order_by(desc(BetaFeedback.created_at)).limit(10))); subs = list(session.scalars(select(CommercialSubscription)))
    ai_cost = session.scalar(select(func.sum(AICostMetricEvent.estimated_cost_usd))) or 0.0; paid = [x for x in subs if x.status == "ACTIVE" and x.plan_id != "FREE"]; mrr = sum(299 if x.plan_id == "PREMIUM_MONTHLY" else 2999 / 12 for x in paid)
    return {"read_only": True, "users": users, "daily_registrations": sum(x.created_at.date() == datetime.now(UTC).date() for x in registrations), "active_users": session.scalar(select(func.count()).select_from(UserAccount).where(UserAccount.status == "ACTIVE")) or 0, "trials": sum(x.status == "TRIAL" for x in subs), "paid_users": len(paid), "estimated_mrr_inr": round(mrr, 2), "estimated_arr_inr": round(mrr * 12, 2), "openai_usage": session.scalar(select(func.count()).select_from(AICostMetricEvent)) or 0, "estimated_ai_cost_usd": round(ai_cost, 6), "average_ai_cost_usd": round(ai_cost / users, 6) if users else 0, "health": "ready", "feedback_count": session.scalar(select(func.count()).select_from(BetaFeedback)) or 0, "subscription_overview": {value: sum(x.status == value for x in subs) for value in {x.status for x in subs}}, "recent_registrations": [{"email": x.email, "created_at": x.created_at} for x in registrations], "recent_feedback": [{"category": x.category, "severity": x.severity, "created_at": x.created_at} for x in feedback_items], "system_status": "RELEASE_CANDIDATE"}
