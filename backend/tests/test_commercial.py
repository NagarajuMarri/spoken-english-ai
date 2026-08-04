from datetime import UTC, datetime, timedelta

import pytest

from backend.app.commercial.entitlements import EntitlementEngine, UsageEnforcer, UsageLimitExceeded, UsageSnapshot
from backend.app.commercial.models import CommercialConfig, PaymentEvent, PlanId, SubscriptionStatus
from backend.app.commercial.payments import DeterministicPaymentProvider, RazorpayBoundary
from backend.app.commercial.service import CommercialService, InvalidTransition


def config(**changes):
    values = {"monthly_price_inr": 299, "yearly_price_inr": 2999, "trial_days": 7, "free_daily_conversations": 5, "free_daily_voice_minutes": 5, "free_daily_grammar_checks": 5, "free_daily_pronunciation_checks": 3, "premium_fair_use_daily_requests": 200, "premium_voice_minutes": 120, "monthly_ai_cost_limit_usd": 20}
    values.update(changes)
    return CommercialConfig(**values)


def service():
    return CommercialService(config(), DeterministicPaymentProvider())


def test_prices_and_trial_are_configuration_not_domain_constants():
    settings = config(monthly_price_inr=499, trial_days=14)
    assert settings.monthly_price_inr == 499 and settings.trial_days == 14
    with pytest.raises(ValueError):
        config(monthly_price_inr=0)


def test_first_trial_activation_and_expiration():
    now = datetime(2026, 8, 4, tzinfo=UTC)
    commercial = service()
    trial = commercial.activate_trial("learner-1", now=now)
    assert trial.status is SubscriptionStatus.TRIAL
    assert trial.current_period_end == now + timedelta(days=7)
    with pytest.raises(ValueError, match="trial_already_used"):
        commercial.activate_trial("learner-1", now=now)
    assert commercial.expire_trials(now=now + timedelta(days=8)) == 1
    assert trial.status is SubscriptionStatus.EXPIRED


@pytest.mark.parametrize(("start", "target"), [
    (SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE),
    (SubscriptionStatus.ACTIVE, SubscriptionStatus.RENEWED),
    (SubscriptionStatus.ACTIVE, SubscriptionStatus.UPGRADED),
    (SubscriptionStatus.ACTIVE, SubscriptionStatus.DOWNGRADED),
    (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAYMENT_FAILED),
    (SubscriptionStatus.PAYMENT_FAILED, SubscriptionStatus.GRACE_PERIOD),
    (SubscriptionStatus.GRACE_PERIOD, SubscriptionStatus.EXPIRED),
    (SubscriptionStatus.CANCELLED, SubscriptionStatus.RESTORED),
])
def test_valid_subscription_transitions(start, target):
    commercial = service()
    item = commercial.activate_trial("learner-1")
    item.status = start
    assert commercial.transition(item.subscription_id, "learner-1", target).status is target


def test_invalid_transition_and_cross_learner_access_are_rejected():
    commercial = service()
    item = commercial.activate_trial("learner-1")
    with pytest.raises(InvalidTransition):
        commercial.transition(item.subscription_id, "learner-1", SubscriptionStatus.RENEWED)
    with pytest.raises(PermissionError):
        commercial.transition(item.subscription_id, "learner-2", SubscriptionStatus.ACTIVE)


def test_entitlements_are_provider_neutral_and_status_aware():
    engine = EntitlementEngine(config())
    free = engine.resolve(PlanId.FREE, SubscriptionStatus.ACTIVE)
    premium = engine.resolve(PlanId.PREMIUM_MONTHLY, SubscriptionStatus.TRIAL)
    expired = engine.resolve(PlanId.PREMIUM_YEARLY, SubscriptionStatus.EXPIRED)
    assert not free.premium_lessons and free.maximum_daily_conversations == 5
    assert premium.premium_lessons and premium.premium_tutors and premium.conversation_history
    assert not expired.premium_lessons


def test_usage_enforcement_covers_limits_and_fair_use():
    limits = EntitlementEngine(config()).resolve(PlanId.FREE, SubscriptionStatus.ACTIVE)
    UsageEnforcer(config()).enforce(limits, UsageSnapshot(conversations=4))
    with pytest.raises(UsageLimitExceeded, match="conversation_limit_reached"):
        UsageEnforcer(config()).enforce(limits, UsageSnapshot(conversations=5))
    with pytest.raises(UsageLimitExceeded, match="ai_cost_limit_reached"):
        UsageEnforcer(config()).enforce(limits, UsageSnapshot(ai_cost_usd=20))


def test_provider_subscription_creation_is_idempotent():
    commercial = service()
    first = commercial.create_provider_subscription("learner-1", PlanId.PREMIUM_MONTHLY, "idem-1")
    second = commercial.create_provider_subscription("learner-1", PlanId.PREMIUM_MONTHLY, "idem-1")
    assert first == second and first.startswith("sub_test_")


def test_signed_webhook_and_duplicate_payment_protection():
    provider = DeterministicPaymentProvider()
    commercial = CommercialService(config(), provider)
    subscription = commercial.activate_trial("learner-1")
    event = PaymentEvent("event-1", "learner-1", subscription.subscription_id, "payment_success", "pay-1")
    payload, signature = provider.sign({"event_id": "event-1"})
    assert commercial.record_payment_event(event, payload, signature)
    assert not commercial.record_payment_event(event, payload, signature)
    with pytest.raises(ValueError, match="invalid_payment_signature"):
        commercial.record_payment_event(PaymentEvent("event-2", "learner-1", subscription.subscription_id, "payment_failed", "pay-2"), payload, "bad")


def test_refund_requires_owner_and_authorization_and_is_audit_logged():
    commercial = service()
    item = commercial.activate_trial("learner-1")
    with pytest.raises(PermissionError):
        commercial.record_refund_request(item.subscription_id, "learner-1", "support", "request", authorized=False)
    refund = commercial.record_refund_request(item.subscription_id, "learner-1", "founder", "duplicate", authorized=True)
    assert refund.status == "REQUESTED"
    assert commercial.audit[-1]["action"] == "refund_requested"


def test_live_razorpay_boundary_is_disabled_without_approved_activation():
    boundary = RazorpayBoundary()
    assert not boundary.verify_signature(b"payload", "signature")
    with pytest.raises(RuntimeError, match="disabled"):
        boundary.create_subscription(learner_id="l1", plan_id=PlanId.PREMIUM_MONTHLY, idempotency_key="idem")


def test_founder_metrics_are_derived_and_labelled_estimates():
    commercial = service()
    item = commercial.activate_trial("learner-1")
    commercial.transition(item.subscription_id, "learner-1", SubscriptionStatus.ACTIVE)
    metrics = commercial.founder_metrics(ai_cost_usd=2.5, conversation_costs={"conversation-1": 0.5})
    assert metrics["paid_users"] == 1
    assert metrics["estimated_mrr_inr"] == 299
    assert metrics["estimated_arr_inr"] == 3588
    assert metrics["ai_cost_per_learner_usd"] == 2.5
    assert metrics["financial_classification"] == "ESTIMATE_NOT_PROVIDER_SETTLEMENT"
