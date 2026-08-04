from __future__ import annotations

from dataclasses import dataclass

from .models import CommercialConfig, Entitlements, PlanId, SubscriptionStatus


class EntitlementEngine:
    """Maps internal plan/status values only; it has no payment-provider dependency."""

    _premium_statuses = {
        SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE, SubscriptionStatus.RENEWED,
        SubscriptionStatus.UPGRADED, SubscriptionStatus.RESTORED, SubscriptionStatus.GRACE_PERIOD,
    }

    def __init__(self, config: CommercialConfig) -> None:
        self.config = config

    def resolve(self, plan: PlanId, status: SubscriptionStatus) -> Entitlements:
        premium = plan is not PlanId.FREE and status in self._premium_statuses
        if not premium:
            return Entitlements(
                self.config.free_daily_conversations,
                self.config.free_daily_voice_minutes,
                self.config.free_daily_grammar_checks,
                self.config.free_daily_pronunciation_checks,
                self.config.free_daily_conversations,
                False, False, False, False, False, False,
                self.config.monthly_request_limit, self.config.token_limit,
            )
        daily_requests = (
            self.config.trial_daily_requests
            if status is SubscriptionStatus.TRIAL
            else self.config.premium_fair_use_daily_requests
        )
        return Entitlements(
            daily_requests,
            self.config.premium_voice_minutes,
            daily_requests,
            daily_requests,
            daily_requests,
            True, self.config.premium_tutors_enabled, True, True, True, True,
            self.config.monthly_request_limit, self.config.token_limit,
        )


@dataclass(frozen=True)
class UsageSnapshot:
    conversations: int = 0
    voice_minutes: float = 0
    grammar_checks: int = 0
    pronunciation_checks: int = 0
    ai_requests: int = 0
    ai_cost_usd: float = 0
    monthly_ai_requests: int = 0
    tokens: int = 0


class UsageLimitExceeded(ValueError):
    pass


class UsageEnforcer:
    def __init__(self, config: CommercialConfig) -> None:
        self.config = config

    def enforce(self, entitlements: Entitlements, usage: UsageSnapshot, *, status: SubscriptionStatus) -> None:
        if status not in EntitlementEngine._premium_statuses and any((
            entitlements.premium_lessons, entitlements.premium_tutors,
            entitlements.progress_analytics, entitlements.conversation_history,
        )):
            raise UsageLimitExceeded("subscription_inactive")
        limits = {
            "conversation": (usage.conversations, entitlements.maximum_daily_conversations),
            "voice": (usage.voice_minutes, entitlements.voice_minutes),
            "grammar": (usage.grammar_checks, entitlements.grammar_checks),
            "pronunciation": (usage.pronunciation_checks, entitlements.pronunciation_checks),
            "ai_requests": (usage.ai_requests, entitlements.ai_requests),
            "ai_cost": (usage.ai_cost_usd, self.config.monthly_ai_cost_limit_usd),
            "monthly_ai_requests": (usage.monthly_ai_requests, entitlements.monthly_ai_requests),
            "tokens": (usage.tokens, entitlements.token_limit),
        }
        for dimension, (used, allowed) in limits.items():
            if used >= allowed:
                raise UsageLimitExceeded(f"{dimension}_limit_reached")
