from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from collections.abc import Callable
from uuid import uuid4

from .models import CommercialConfig, PaymentEvent, PlanId, RefundRecord, Subscription, SubscriptionStatus
from .payments import PaymentBoundary


class InvalidTransition(ValueError):
    pass


class CommercialService:
    _transitions = {
        SubscriptionStatus.TRIAL: {SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED},
        SubscriptionStatus.ACTIVE: {SubscriptionStatus.RENEWED, SubscriptionStatus.UPGRADED, SubscriptionStatus.DOWNGRADED, SubscriptionStatus.GRACE_PERIOD, SubscriptionStatus.CANCELLED, SubscriptionStatus.PAYMENT_FAILED},
        SubscriptionStatus.RENEWED: {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAYMENT_FAILED},
        SubscriptionStatus.UPGRADED: {SubscriptionStatus.ACTIVE},
        SubscriptionStatus.DOWNGRADED: {SubscriptionStatus.ACTIVE},
        SubscriptionStatus.GRACE_PERIOD: {SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED, SubscriptionStatus.PAYMENT_FAILED},
        SubscriptionStatus.PAYMENT_FAILED: {SubscriptionStatus.GRACE_PERIOD, SubscriptionStatus.EXPIRED, SubscriptionStatus.RESTORED},
        SubscriptionStatus.CANCELLED: {SubscriptionStatus.RESTORED, SubscriptionStatus.EXPIRED},
        SubscriptionStatus.EXPIRED: {SubscriptionStatus.RESTORED},
        SubscriptionStatus.RESTORED: {SubscriptionStatus.ACTIVE},
    }

    def __init__(self, config: CommercialConfig, provider: PaymentBoundary, *, clock: Callable[[], datetime] | None = None) -> None:
        self.config, self.provider = config, provider
        self._clock = clock or (lambda: datetime.now(UTC))
        self.subscriptions: dict[str, Subscription] = {}
        self.events: dict[str, PaymentEvent] = {}
        self.refunds: dict[str, RefundRecord] = {}
        self.audit: list[dict] = []
        self._idempotency: dict[str, tuple[str, PlanId, str]] = {}

    def activate_trial(self, learner_id: str, *, now: datetime | None = None) -> Subscription:
        if any(item.learner_id == learner_id for item in self.subscriptions.values()):
            raise ValueError("trial_already_used")
        now = self._aware(now or self._clock())
        item = Subscription(str(uuid4()), learner_id, PlanId.PREMIUM_MONTHLY, SubscriptionStatus.TRIAL, now, now + timedelta(days=self.config.trial_days))
        self.subscriptions[item.subscription_id] = item
        self._audit("trial_activated", learner_id, item.subscription_id)
        return item

    def create_provider_subscription(self, learner_id: str, plan: PlanId, idempotency_key: str) -> str:
        if idempotency_key in self._idempotency:
            owner, stored_plan, reference = self._idempotency[idempotency_key]
            if owner != learner_id or stored_plan is not plan:
                raise ValueError("idempotency_key_conflict")
            return reference
        reference = self.provider.create_subscription(learner_id=learner_id, plan_id=plan, idempotency_key=idempotency_key)
        self._idempotency[idempotency_key] = (learner_id, plan, reference)
        return reference

    def transition(self, subscription_id: str, learner_id: str, target: SubscriptionStatus) -> Subscription:
        item = self._owned(subscription_id, learner_id)
        if target not in self._transitions.get(item.status, set()):
            raise InvalidTransition(f"{item.status}_to_{target}")
        item.status, item.version = target, item.version + 1
        self._audit("subscription_transition", learner_id, subscription_id, target=target.value)
        return item

    def record_payment_event(self, event: PaymentEvent, payload: bytes, signature: str) -> bool:
        if event.event_id in self.events:
            return False
        if not self.provider.verify_signature(payload, signature):
            raise ValueError("invalid_payment_signature")
        try:
            content = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_webhook_payload") from exc
        expected = {
            "event_id": event.event_id,
            "learner_id": event.learner_id,
            "subscription_id": event.subscription_id,
            "event_type": event.event_type,
            "provider_reference": event.provider_reference,
        }
        if content != expected:
            raise ValueError("webhook_identity_mismatch")
        self._owned(event.subscription_id, event.learner_id)
        self.events[event.event_id] = event
        self._audit(event.event_type, event.learner_id, event.subscription_id, event_id=event.event_id)
        return True

    def record_refund_request(self, subscription_id: str, learner_id: str, requested_by: str, reason: str, *, authorized: bool) -> RefundRecord:
        self._owned(subscription_id, learner_id)
        if not authorized:
            raise PermissionError("refund_not_authorized")
        record = RefundRecord(str(uuid4()), learner_id, subscription_id, reason, requested_by)
        self.refunds[record.refund_id] = record
        self._audit("refund_requested", learner_id, subscription_id, refund_id=record.refund_id)
        return record

    def expire_trials(self, *, now: datetime | None = None) -> int:
        now = self._aware(now or self._clock())
        expired = 0
        for item in self.subscriptions.values():
            if item.status is SubscriptionStatus.TRIAL and item.current_period_end <= now:
                item.status, item.version = SubscriptionStatus.EXPIRED, item.version + 1
                expired += 1
        return expired

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone_aware_clock_required")
        return value.astimezone(UTC)

    def founder_metrics(self, *, ai_cost_usd: float = 0, conversation_costs: dict | None = None) -> dict:
        subscriptions = tuple(self.subscriptions.values())
        learners = {item.learner_id for item in subscriptions}
        active_statuses = {SubscriptionStatus.ACTIVE, SubscriptionStatus.RENEWED, SubscriptionStatus.UPGRADED, SubscriptionStatus.RESTORED}
        paid = [item for item in subscriptions if item.plan_id is not PlanId.FREE and item.status in active_statuses]
        trials = [item for item in subscriptions if item.status is SubscriptionStatus.TRIAL]
        monthly = sum(item.plan_id is PlanId.PREMIUM_MONTHLY for item in paid)
        yearly = sum(item.plan_id is PlanId.PREMIUM_YEARLY for item in paid)
        estimated_mrr = monthly * self.config.monthly_price_inr + yearly * self.config.yearly_price_inr / 12
        return {
            "new_users": len(learners),
            "active_users": len({item.learner_id for item in subscriptions if item.status in active_statuses}),
            "paid_users": len({item.learner_id for item in paid}),
            "trial_users": len({item.learner_id for item in trials}),
            "conversion_rate": len({item.learner_id for item in paid}) / len(learners) if learners else 0.0,
            "estimated_mrr_inr": round(estimated_mrr, 2),
            "estimated_arr_inr": round(estimated_mrr * 12, 2),
            "ai_cost_usd": ai_cost_usd,
            "ai_cost_per_learner_usd": ai_cost_usd / len(learners) if learners else 0.0,
            "ai_cost_per_conversation_usd": conversation_costs or {},
            "subscription_counts": {status.value: sum(item.status is status for item in subscriptions) for status in SubscriptionStatus},
            "financial_classification": "ESTIMATE_NOT_PROVIDER_SETTLEMENT",
        }

    def _owned(self, subscription_id: str, learner_id: str) -> Subscription:
        item = self.subscriptions.get(subscription_id)
        if item is None or item.learner_id != learner_id:
            raise PermissionError("subscription_not_owned")
        return item

    def _audit(self, action: str, learner_id: str, subscription_id: str, **details) -> None:
        self.audit.append({"action": action, "learner_id": learner_id, "subscription_id": subscription_id, "details": details})
