"""Offline Milestone 10 lifecycle demonstration; no payment network is used."""

from datetime import UTC, datetime, timedelta

from backend.app.commercial.models import CommercialConfig, PaymentEvent, SubscriptionStatus
from backend.app.commercial.payments import DeterministicPaymentProvider
from backend.app.commercial.service import CommercialService

config = CommercialConfig(299, 2999, 7, 5, 5, 5, 3, 200, 120, 20)
provider = DeterministicPaymentProvider()
service = CommercialService(config, provider)
now = datetime(2026, 8, 4, tzinfo=UTC)
trial = service.activate_trial("learner-demo", now=now)
payload, signature = provider.sign({"event_id": "payment-1", "learner_id": "learner-demo", "subscription_id": trial.subscription_id, "event_type": "payment_success", "provider_reference": "pay-test"})
service.record_payment_event(PaymentEvent("payment-1", "learner-demo", trial.subscription_id, "payment_success", "pay-test"), payload, signature)
service.transition(trial.subscription_id, "learner-demo", SubscriptionStatus.ACTIVE)
service.transition(trial.subscription_id, "learner-demo", SubscriptionStatus.RENEWED)
service.transition(trial.subscription_id, "learner-demo", SubscriptionStatus.ACTIVE)
service.transition(trial.subscription_id, "learner-demo", SubscriptionStatus.UPGRADED)
service.transition(trial.subscription_id, "learner-demo", SubscriptionStatus.ACTIVE)
service.transition(trial.subscription_id, "learner-demo", SubscriptionStatus.DOWNGRADED)
service.transition(trial.subscription_id, "learner-demo", SubscriptionStatus.ACTIVE)
service.transition(trial.subscription_id, "learner-demo", SubscriptionStatus.PAYMENT_FAILED)
service.transition(trial.subscription_id, "learner-demo", SubscriptionStatus.GRACE_PERIOD)
service.transition(trial.subscription_id, "learner-demo", SubscriptionStatus.EXPIRED)
service.transition(trial.subscription_id, "learner-demo", SubscriptionStatus.RESTORED)
refund = service.record_refund_request(trial.subscription_id, "learner-demo", "founder", "deterministic example", authorized=True)
assert trial.current_period_end == now + timedelta(days=7)
print({"trial_days": config.trial_days, "status": trial.status, "refund": refund.status, "provider": provider.provider_id, "live": False})
