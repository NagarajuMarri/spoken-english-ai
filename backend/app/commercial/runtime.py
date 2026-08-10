from __future__ import annotations

from datetime import UTC, datetime
from math import ceil
from typing import Any, cast

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.models import (
    AICostMetricEvent,
    AIUsageRecord,
    AITurnAttempt,
    Conversation,
    Learner,
    ProviderCallEvent,
    VoiceProcessingAttempt,
    VoiceSession,
)
from backend.app.models.entities import CommercialAuditEvent, CommercialSubscription

from .entitlements import EntitlementEngine
from .models import CommercialConfig, Entitlements, PlanId, SubscriptionStatus


class RuntimeEntitlementService:
    """Resolve persisted subscription state and enforce the learner-facing quotas."""

    def __init__(
        self,
        session: Session,
        config: CommercialConfig,
        *,
        now: datetime | None = None,
    ) -> None:
        self.session = session
        self.config = config
        self.now = (now or datetime.now(UTC)).astimezone(UTC)

    def view(self, learner_id: str, *, payment_mode: str) -> dict:
        subscription = self._current_subscription(learner_id)
        plan, entitlement_status, public_status = self._state(subscription)
        entitlements = EntitlementEngine(self.config).resolve(plan, entitlement_status)
        remaining_days = 0
        if subscription is not None and public_status == SubscriptionStatus.TRIAL.value:
            remaining_days = max(
                0,
                ceil((self._aware(subscription.current_period_end) - self.now).total_seconds() / 86_400),
            )
        return {
            "plan_id": plan.value,
            "status": public_status,
            "trial_remaining_days": remaining_days,
            "payment_mode": payment_mode,
            "entitlements": {
                "daily_conversations": entitlements.maximum_daily_conversations,
                "voice_minutes": entitlements.voice_minutes,
            },
            "fair_use": "Daily limits are measured and enforced by the server; text review remains available when voice allowance ends.",
        }

    def enforce_conversation(self, learner_id: str) -> None:
        entitlements = self._entitlements(learner_id)
        self._lock_learner(learner_id)
        text_conversations = self.session.scalar(
            select(func.count()).select_from(Conversation).where(
                Conversation.learner_id == learner_id,
                Conversation.created_at >= self._day_start(),
            )
        ) or 0
        voice_conversations = self.session.scalar(
            select(func.count()).select_from(VoiceSession).where(
                VoiceSession.learner_id == learner_id,
                VoiceSession.created_at >= self._day_start(),
            )
        ) or 0
        used = text_conversations + voice_conversations
        if used >= entitlements.maximum_daily_conversations:
            raise AppError(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "daily_conversation_limit_reached",
                "Your daily new-conversation limit has been reached. You can continue an existing conversation.",
            )

    def enforce_ai_request(self, learner_id: str, *, new_request: bool = True) -> None:
        entitlements = self._entitlements(learner_id)
        self._lock_learner(learner_id)
        if new_request:
            ai_turns = self.session.scalar(
                select(func.count()).select_from(AITurnAttempt).where(
                    AITurnAttempt.learner_id == learner_id,
                    AITurnAttempt.created_at >= self._day_start(),
                )
            ) or 0
            voice_turns = self.session.scalar(
                select(func.count()).select_from(VoiceProcessingAttempt).where(
                    VoiceProcessingAttempt.learner_id == learner_id,
                    VoiceProcessingAttempt.created_at >= self._day_start(),
                )
            ) or 0
            if ai_turns + voice_turns >= entitlements.ai_requests:
                self._limit("daily_ai_request_limit_reached", "Your daily tutor-request limit has been reached.")
        self._enforce_provider_budget(learner_id, entitlements)

    def enforce_provider_budget(self, learner_id: str) -> None:
        entitlements = self._entitlements(learner_id)
        self._lock_learner(learner_id)
        self._enforce_provider_budget(learner_id, entitlements)

    def _enforce_provider_budget(self, learner_id: str, entitlements: Entitlements) -> None:
        monthly_requests = self.session.scalar(
            select(func.sum(ProviderCallEvent.request_count)).where(
                ProviderCallEvent.learner_id == learner_id,
                ProviderCallEvent.occurred_at >= self._month_start(),
            )
        ) or 0
        tokens = self.session.scalar(
            select(func.sum(AIUsageRecord.input_units + AIUsageRecord.output_units)).where(
                AIUsageRecord.learner_id == learner_id,
                AIUsageRecord.occurred_at >= self._month_start(),
                AIUsageRecord.provider_kind.in_(("llm", "language_review", "voice_pipeline", "tts")),
            )
        ) or 0
        ai_cost = self.session.scalar(
            select(func.sum(AICostMetricEvent.estimated_cost_usd)).where(
                AICostMetricEvent.learner_id == learner_id,
                AICostMetricEvent.occurred_at >= self._month_start(),
            )
        ) or 0
        if monthly_requests >= entitlements.monthly_ai_requests:
            self._limit("monthly_ai_request_limit_reached", "Your monthly tutor-request limit has been reached.")
        if tokens >= entitlements.token_limit:
            self._limit("monthly_ai_token_limit_reached", "Your monthly tutor usage limit has been reached.")
        if ai_cost >= self.config.monthly_ai_cost_limit_usd:
            self._limit("monthly_ai_cost_limit_reached", "Tutor service is paused because the monthly safety ceiling was reached.")

    def enforce_voice(self, learner_id: str, requested_duration_ms: int) -> None:
        entitlements = self._entitlements(learner_id)
        self._lock_learner(learner_id)
        used_ms = self.session.scalar(
            select(func.sum(ProviderCallEvent.duration_ms)).where(
                ProviderCallEvent.learner_id == learner_id,
                ProviderCallEvent.operation_kind == "stt",
                ProviderCallEvent.occurred_at >= self._day_start(),
            )
        ) or 0
        if used_ms + requested_duration_ms > entitlements.voice_minutes * 60_000:
            raise AppError(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "daily_voice_limit_reached",
                "Your daily voice allowance has been reached. You can continue practising with text.",
            )

    def _entitlements(self, learner_id: str) -> Entitlements:
        subscription = self._current_subscription(learner_id)
        plan, entitlement_status, _ = self._state(subscription)
        return EntitlementEngine(self.config).resolve(plan, entitlement_status)

    def _current_subscription(self, learner_id: str) -> CommercialSubscription | None:
        item = self.session.scalar(
            select(CommercialSubscription)
            .where(CommercialSubscription.learner_id == learner_id)
            .order_by(CommercialSubscription.created_at.desc())
            .limit(1)
        )
        expirable_statuses = {
            SubscriptionStatus.TRIAL.value,
            SubscriptionStatus.ACTIVE.value,
            SubscriptionStatus.GRACE_PERIOD.value,
            SubscriptionStatus.RENEWED.value,
            SubscriptionStatus.UPGRADED.value,
            SubscriptionStatus.RESTORED.value,
        }
        if (
            item is not None
            and item.status in expirable_statuses
            and self._aware(item.current_period_end) <= self.now
        ):
            self._expire_once(item)
        return item

    def _expire_once(self, item: CommercialSubscription) -> None:
        prior_status = item.status
        expired = cast(CursorResult[Any], self.session.execute(
            update(CommercialSubscription)
            .where(
                CommercialSubscription.id == item.id,
                CommercialSubscription.status == prior_status,
                CommercialSubscription.current_period_end <= self.now,
            )
            .values(
                status=SubscriptionStatus.EXPIRED.value,
                version=CommercialSubscription.version + 1,
                updated_at=self.now,
            )
            .execution_options(synchronize_session=False)
        )).rowcount == 1
        if expired:
            self.session.add(
                CommercialAuditEvent(
                    subscription_id=item.id,
                    learner_id=item.learner_id,
                    action=(
                        "TRIAL_EXPIRED"
                        if prior_status == SubscriptionStatus.TRIAL.value
                        else "SUBSCRIPTION_EXPIRED"
                    ),
                    outcome="RECORDED",
                    metadata_json={"source": "runtime_entitlement_resolution"},
                )
            )
        self.session.commit()
        self.session.refresh(item)

    @staticmethod
    def _state(
        subscription: CommercialSubscription | None,
    ) -> tuple[PlanId, SubscriptionStatus, str]:
        if subscription is None:
            return PlanId.FREE, SubscriptionStatus.ACTIVE, "FREE"
        try:
            plan = PlanId(subscription.plan_id)
        except ValueError:
            plan = PlanId.FREE
        try:
            subscription_status = SubscriptionStatus(subscription.status)
        except ValueError:
            subscription_status = SubscriptionStatus.EXPIRED
        return plan, subscription_status, subscription_status.value

    def _lock_learner(self, learner_id: str) -> None:
        # PostgreSQL serializes quota decisions for one learner. SQLite ignores
        # FOR UPDATE, which is sufficient for the repository's sequential tests.
        self.session.execute(
            select(Learner.id).where(Learner.id == learner_id).with_for_update()
        ).scalar_one()

    def _day_start(self) -> datetime:
        return self.now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _month_start(self) -> datetime:
        return self.now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _limit(code: str, message: str) -> None:
        raise AppError(status.HTTP_429_TOO_MANY_REQUESTS, code, message)
