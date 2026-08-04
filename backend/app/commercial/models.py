from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class PlanId(StrEnum):
    FREE = "FREE"
    PREMIUM_MONTHLY = "PREMIUM_MONTHLY"
    PREMIUM_YEARLY = "PREMIUM_YEARLY"


class SubscriptionStatus(StrEnum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    GRACE_PERIOD = "GRACE_PERIOD"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    RENEWED = "RENEWED"
    UPGRADED = "UPGRADED"
    DOWNGRADED = "DOWNGRADED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    RESTORED = "RESTORED"


@dataclass(frozen=True)
class CommercialConfig:
    monthly_price_inr: int
    yearly_price_inr: int
    trial_days: int
    free_daily_conversations: int
    free_daily_voice_minutes: int
    free_daily_grammar_checks: int
    free_daily_pronunciation_checks: int
    premium_fair_use_daily_requests: int
    premium_voice_minutes: int
    monthly_ai_cost_limit_usd: float
    advertisements_enabled: bool = False
    premium_tutors_enabled: bool = True

    def __post_init__(self) -> None:
        if any(value <= 0 for value in (
            self.monthly_price_inr, self.yearly_price_inr, self.trial_days,
            self.free_daily_conversations, self.free_daily_voice_minutes,
            self.free_daily_grammar_checks, self.free_daily_pronunciation_checks,
            self.premium_fair_use_daily_requests, self.premium_voice_minutes,
            self.monthly_ai_cost_limit_usd,
        )):
            raise ValueError("Commercial configuration values must be positive")


@dataclass
class Subscription:
    subscription_id: str
    learner_id: str
    plan_id: PlanId
    status: SubscriptionStatus
    started_at: datetime
    current_period_end: datetime
    provider_reference: str | None = None
    version: int = 1


@dataclass(frozen=True)
class PaymentEvent:
    event_id: str
    learner_id: str
    subscription_id: str
    event_type: str
    provider_reference: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class RefundRecord:
    refund_id: str
    learner_id: str
    subscription_id: str
    reason: str
    requested_by: str
    status: str = "REQUESTED"


@dataclass(frozen=True)
class Entitlements:
    maximum_daily_conversations: int
    voice_minutes: int
    grammar_checks: int
    pronunciation_checks: int
    ai_requests: int
    premium_lessons: bool
    premium_tutors: bool
    progress_analytics: bool
    conversation_history: bool
    pronunciation_coaching: bool
    vocabulary_coaching: bool
