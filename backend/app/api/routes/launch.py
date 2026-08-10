from datetime import UTC, datetime, timedelta
from pathlib import PurePath

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.commercial.runtime import RuntimeEntitlementService
from backend.app.core.errors import AppError
from backend.app.core.operations import enforce_rate_limit
from backend.app.core.security import Principal, current_principal
from backend.app.db.session import get_db
from backend.app.models import BetaFeedback, UserAccount
from backend.app.models.entities import (
    AICostMetricEvent,
    CommercialAuditEvent,
    CommercialSubscription,
    Conversation,
    ConversationEvaluation,
    LessonSession,
    ProgressRecord,
)
from backend.app.services.learning import LearningService

router = APIRouter(prefix="/api/v1/launch", tags=["launch-readiness"])


class Feedback(BaseModel):
    rating: int = Field(ge=1, le=5)
    category: str = Field(pattern="^(onboarding|lesson|voice|support|subscription|other)$")
    severity: str = Field(pattern="^(LOW|MEDIUM|HIGH|BLOCKING)$")
    message: str = Field(min_length=3, max_length=1000)
    contact_allowed: bool = False
    screenshot_name: str | None = Field(default=None, max_length=200)


def require_founder(request: Request, principal: Principal) -> None:
    if (
        not principal.user.email_verified
        or principal.user.email.lower() not in request.app.state.settings.founders()
    ):
        raise AppError(status.HTTP_403_FORBIDDEN, "founder_access_required", "This read-only dashboard is unavailable.")


@router.get("/config")
def launch_config(request: Request):
    settings = request.app.state.settings
    return {"product_name": settings.product_name, "version": settings.release_version, "closed_beta": settings.closed_beta_enabled, "razorpay_mode": settings.razorpay_mode, "payments_enabled": settings.razorpay_enabled, "support_email": settings.support_email, "provider_policy": "OPENAI_FIRST", "release_state": "RELEASE_CANDIDATE_NOT_PUBLIC"}


@router.post("/feedback", status_code=202)
def feedback(data: Feedback, request: Request, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    enforce_rate_limit(request, "authenticated_burst", principal.user.id)
    record = BetaFeedback(learner_id=principal.learner.id, category=data.category, severity=data.severity, message=data.message, contact_allowed=data.contact_allowed, screenshot_name=PurePath(data.screenshot_name).name if data.screenshot_name else None)
    session.add(record); session.commit(); request.app.state.metrics.increment("beta_feedback")
    return {"accepted": True, "feedback_id": record.id, "message": "Thank you. Your feedback was received safely."}


@router.get("/subscription")
def subscription(
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    return RuntimeEntitlementService(
        session,
        request.app.state.commercial_service.config,
    ).view(principal.learner.id, payment_mode=request.app.state.settings.razorpay_mode)


@router.post("/subscription/trial", status_code=201)
def start_trial(request: Request, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    enforce_rate_limit(request, "authenticated_burst", principal.user.id)
    if session.scalar(select(CommercialSubscription).where(CommercialSubscription.learner_id == principal.learner.id)) is not None:
        raise AppError(409, "trial_already_used", "A trial or subscription already exists.")
    now = datetime.now(UTC)
    item = CommercialSubscription(
        learner_id=principal.learner.id,
        plan_id="PREMIUM_MONTHLY",
        status="TRIAL",
        provider_id="razorpay-test",
        trial_started_at=now,
        current_period_end=now + timedelta(days=request.app.state.commercial_service.config.trial_days),
    )
    session.add(item)
    try:
        session.flush()
        session.add(CommercialAuditEvent(
            subscription_id=item.id,
            learner_id=principal.learner.id,
            action="TRIAL_ACTIVATED",
            outcome="RECORDED",
            metadata_json={"payment_mode": "test"},
        ))
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "trial_already_used", "A trial or subscription already exists.") from exc
    return {"status": "TRIAL", "payment_mode": request.app.state.settings.razorpay_mode}


@router.post("/subscription/upgrade", status_code=202)
def request_upgrade(
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    enforce_rate_limit(request, "authenticated_burst", principal.user.id)
    if request.app.state.settings.razorpay_mode != "test":
        raise AppError(503, "payment_mode_unavailable", "Payments are unavailable.")
    subscription = session.scalar(
        select(CommercialSubscription).where(
            CommercialSubscription.learner_id == principal.learner.id
        )
    )
    session.add(CommercialAuditEvent(
        subscription_id=subscription.id if subscription else None,
        learner_id=principal.learner.id,
        action="TEST_UPGRADE_PREVIEWED",
        outcome="RECORDED",
        metadata_json={"real_charge": False},
    ))
    session.commit()
    return {"status": "UPGRADE_PREVIEW", "payment_mode": "test", "real_charge": False}


@router.get("/progress")
def progress(principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    learner_id = principal.learner.id
    evaluations = list(session.scalars(select(ConversationEvaluation).join(LessonSession).where(LessonSession.learner_id == learner_id)))
    average = lambda name: round(sum(getattr(x, name) for x in evaluations) / len(evaluations), 1) if evaluations else None
    conversations = session.scalar(select(func.count()).select_from(Conversation).where(Conversation.learner_id == learner_id)) or 0
    learning = LearningService(session)
    learning_progress = learning.progress(learner_id)
    today = datetime.now(UTC).date()
    streak = learning.streak(learner_id, today=today)
    weekly_activity = session.scalar(select(func.count()).select_from(ProgressRecord).where(
        ProgressRecord.learner_id == learner_id,
        ProgressRecord.lesson_id.is_not(None),
        ProgressRecord.practice_date >= today - timedelta(days=6),
    )) or 0
    monthly_activity = session.scalar(select(func.count()).select_from(ProgressRecord).where(
        ProgressRecord.learner_id == learner_id,
        ProgressRecord.lesson_id.is_not(None),
        ProgressRecord.practice_date >= today.replace(day=1),
    )) or 0
    achievements = []
    if learning_progress["completed_lessons"] >= 1:
        achievements.append("Completed first lesson")
    if learning_progress["completed_lessons"] >= 5:
        achievements.append("Completed 5 lessons")
    if streak["longest_streak"] >= 3:
        achievements.append("Built a 3-day practice streak")
    if conversations >= 1:
        achievements.append("Started first conversation")
    return {
        "scores": {
            "grammar": average("grammar_score"),
            "vocabulary": average("vocabulary_score"),
            "pronunciation": None,
            "confidence": average("confidence_score"),
            "fluency": average("fluency_score"),
        },
        "completed_lessons": learning_progress["completed_lessons"],
        "daily_streak": streak["current_streak"],
        "weekly_activity": weekly_activity,
        "monthly_activity": monthly_activity,
        "learning_goal": principal.learner.learning_goal,
        "recent_achievements": achievements,
        "conversation_history_summary": {
            "conversations": conversations,
            "recent_sessions": min(conversations, 5),
        },
    }


@router.get("/founder-dashboard")
def founder_dashboard(request: Request, principal: Principal = Depends(current_principal), session: Session = Depends(get_db)):
    require_founder(request, principal)
    users = session.scalar(select(func.count()).select_from(UserAccount)) or 0
    registrations = list(session.scalars(select(UserAccount).order_by(desc(UserAccount.created_at)).limit(10)))
    feedback_items = list(session.scalars(select(BetaFeedback).order_by(desc(BetaFeedback.created_at)).limit(10)))
    subs = list(session.scalars(select(CommercialSubscription)))
    ai_cost = session.scalar(select(func.sum(AICostMetricEvent.estimated_cost_usd))) or 0.0
    now = datetime.now(UTC)
    expirable_statuses = {
        "TRIAL", "ACTIVE", "GRACE_PERIOD", "RENEWED", "UPGRADED", "RESTORED",
    }

    def effective_status(item: CommercialSubscription) -> str:
        period_end = item.current_period_end
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=UTC)
        if item.status in expirable_statuses and period_end <= now:
            return "EXPIRED"
        return item.status

    effective_statuses = [effective_status(item) for item in subs]
    paid_statuses = {"ACTIVE", "RENEWED", "UPGRADED", "RESTORED"}
    paid_plans = {"PREMIUM_MONTHLY", "PREMIUM_YEARLY"}
    paid = [
        item
        for item, item_status in zip(subs, effective_statuses)
        if item_status in paid_statuses
        and item.plan_id in paid_plans
        and (item.current_period_end.replace(tzinfo=item.current_period_end.tzinfo or UTC) > now)
    ]
    settings = request.app.state.settings
    mrr = sum(
        settings.commercial_monthly_price_inr
        if item.plan_id == "PREMIUM_MONTHLY"
        else settings.commercial_yearly_price_inr / 12
        for item in paid
    )
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_registrations = session.scalar(
        select(func.count()).select_from(UserAccount).where(
            UserAccount.created_at >= day_start,
            UserAccount.created_at < day_start + timedelta(days=1),
        )
    ) or 0
    return {
        "read_only": True,
        "users": users,
        "daily_registrations": daily_registrations,
        "active_users": session.scalar(select(func.count()).select_from(UserAccount).where(UserAccount.status == "ACTIVE")) or 0,
        "trials": sum(value == "TRIAL" for value in effective_statuses),
        "paid_users": len(paid),
        "estimated_mrr_inr": round(mrr, 2),
        "estimated_arr_inr": round(mrr * 12, 2),
        "openai_usage": session.scalar(select(func.count()).select_from(AICostMetricEvent)) or 0,
        "estimated_ai_cost_usd": round(ai_cost, 6),
        "average_ai_cost_usd": round(ai_cost / users, 6) if users else 0,
        "health": "CHECK_HEALTH_READY",
        "health_endpoint": "/health/ready",
        "feedback_count": session.scalar(select(func.count()).select_from(BetaFeedback)) or 0,
        "subscription_overview": {
            value: effective_statuses.count(value) for value in set(effective_statuses)
        },
        "recent_registrations": [{"email": x.email, "created_at": x.created_at} for x in registrations],
        "recent_feedback": [{"category": x.category, "severity": x.severity, "created_at": x.created_at} for x in feedback_items],
        "system_status": "RELEASE_CANDIDATE",
    }
