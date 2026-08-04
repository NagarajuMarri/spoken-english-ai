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
            )
        return Entitlements(
            self.config.premium_fair_use_daily_requests,
            self.config.premium_voice_minutes,
            self.config.premium_fair_use_daily_requests,
            self.config.premium_fair_use_daily_requests,
            self.config.premium_fair_use_daily_requests,
            True, self.config.premium_tutors_enabled, True, True, True, True,
        )


@dataclass(frozen=True)
class UsageSnapshot:
    conversations: int = 0
    voice_minutes: float = 0
    grammar_checks: int = 0
    pronunciation_checks: int = 0
    ai_requests: int = 0
    ai_cost_usd: float = 0


class UsageLimitExceeded(ValueError):
    pass


class UsageEnforcer:
    def __init__(self, config: CommercialConfig) -> None:
        self.config = config

    def enforce(self, entitlements: Entitlements, usage: UsageSnapshot) -> None:
        limits = {
            "conversation": (usage.conversations, entitlements.maximum_daily_conversations),
            "voice": (usage.voice_minutes, entitlements.voice_minutes),
            "grammar": (usage.grammar_checks, entitlements.grammar_checks),
            "pronunciation": (usage.pronunciation_checks, entitlements.pronunciation_checks),
            "ai_requests": (usage.ai_requests, entitlements.ai_requests),
            "ai_cost": (usage.ai_cost_usd, self.config.monthly_ai_cost_limit_usd),
        }
        for dimension, (used, allowed) in limits.items():
            if used >= allowed:
                raise UsageLimitExceeded(f"{dimension}_limit_reached")
