from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Protocol

from .models import PlanId


class PaymentBoundary(Protocol):
    provider_id: str

    def create_subscription(self, *, learner_id: str, plan_id: PlanId, idempotency_key: str) -> str: ...
    def verify_signature(self, payload: bytes, signature: str) -> bool: ...


class RazorpayBoundary:
    provider_id = "razorpay"

    def __init__(self, webhook_secret: str | None = None) -> None:
        self._secret = webhook_secret

    def create_subscription(self, *, learner_id: str, plan_id: PlanId, idempotency_key: str) -> str:
        raise RuntimeError("Live Razorpay subscription creation is disabled until credentials are approved")

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        if not self._secret:
            return False
        expected = hmac.new(self._secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


@dataclass
class DeterministicPaymentProvider:
    provider_id: str = "deterministic-razorpay"
    webhook_secret: str = "deterministic-test-secret"

    def create_subscription(self, *, learner_id: str, plan_id: PlanId, idempotency_key: str) -> str:
        digest = hashlib.sha256(f"{learner_id}:{plan_id}:{idempotency_key}".encode()).hexdigest()[:16]
        return f"sub_test_{digest}"

    def sign(self, payload: dict) -> tuple[bytes, str]:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.new(self.webhook_secret.encode(), encoded, hashlib.sha256).hexdigest()
        return encoded, signature

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        expected = hmac.new(self.webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
