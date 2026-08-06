from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import re
import time
from typing import Protocol
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi import status
from backend.app.core.errors import AppError


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
logger = logging.getLogger("spoken_english.operations")


class Metrics(Protocol):
    def increment(self, name: str, value: int = 1) -> None: ...
    def observe(self, name: str, value: float) -> None: ...
    def gauge(self, name: str, value: float) -> None: ...


class InMemoryMetrics:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.observations: dict[str, list[float]] = {}
        self.gauges: dict[str, float] = {}

    def increment(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def observe(self, name: str, value: float) -> None:
        self.observations.setdefault(name, []).append(value)

    def gauge(self, name: str, value: float) -> None:
        self.gauges[name] = value

    def snapshot(self) -> dict:
        return {"counters": self.counters, "observations": self.observations, "gauges": self.gauges}


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


class RateLimiter(Protocol):
    def decide(self, policy: RateLimitPolicy, key: str) -> RateLimitDecision: ...
    def reset(self, policy: RateLimitPolicy, key: str) -> None: ...


class InMemoryRateLimiter:
    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self._buckets: dict[tuple[str, str], tuple[int, float]] = {}

    def decide(self, policy: RateLimitPolicy, key: str) -> RateLimitDecision:
        now = self.clock()
        bucket_key = (policy.name, key)
        count, started = self._buckets.get(bucket_key, (0, now))
        if now - started >= policy.window_seconds:
            count, started = 0, now
        if count >= policy.limit:
            return RateLimitDecision(False, max(1, int(policy.window_seconds - (now - started))))
        self._buckets[bucket_key] = (count + 1, started)
        return RateLimitDecision(True)

    def reset(self, policy: RateLimitPolicy, key: str) -> None:
        self._buckets.pop((policy.name, key), None)


class RedisRateLimiter:
    """Adapter boundary; a Redis client is injected by production composition."""

    def __init__(self, client) -> None:
        self.client = client

    def decide(self, policy: RateLimitPolicy, key: str) -> RateLimitDecision:
        namespaced = f"rate:{policy.name}:{key}"
        pipeline = self.client.pipeline()
        pipeline.incr(namespaced)
        pipeline.ttl(namespaced)
        count, ttl = pipeline.execute()
        if count == 1 or ttl < 0:
            self.client.expire(namespaced, policy.window_seconds)
            ttl = policy.window_seconds
        return RateLimitDecision(count <= policy.limit, max(1, int(ttl)) if count > policy.limit else 0)

    def reset(self, policy: RateLimitPolicy, key: str) -> None:
        self.client.delete(f"rate:{policy.name}:{key}")


RATE_POLICIES = {
    "login_email": RateLimitPolicy("login_email", 10, 60),
    "login_network": RateLimitPolicy("login_network", 20, 60),
    "registration": RateLimitPolicy("registration", 10, 60),
    "refresh": RateLimitPolicy("refresh", 30, 60),
    "voice_turn": RateLimitPolicy("voice_turn", 30, 60),
    "authenticated_burst": RateLimitPolicy("authenticated_burst", 120, 60),
}


def enforce_rate_limit(request: Request, policy_name: str, key: str) -> None:
    decision = request.app.state.rate_limiter.decide(RATE_POLICIES[policy_name], key)
    if not decision.allowed:
        request.app.state.metrics.increment("throttled_requests")
        raise AppError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            "Too many requests.",
            {"Retry-After": str(decision.retry_after)},
        )

def privacy_key(value: str) -> str:
    return hashlib.sha256(f"spoken-english-privacy:{value}".encode()).hexdigest()


def audit_event(session, event_type: str, *, principal=None, outcome="SUCCEEDED", reason_code=None, metadata=None):
    from backend.app.models import SecurityAuditEvent
    event = SecurityAuditEvent(
        event_type=event_type,
        user_id=principal.user.id if principal else None,
        learner_id=principal.learner.id if principal else None,
        request_id=getattr(principal, "request_id", None),
        correlation_id=getattr(principal, "correlation_id", None),
        outcome=outcome,
        reason_code=reason_code,
        privacy_minimised_network_key=getattr(principal, "network_key", None),
        user_agent_summary=getattr(principal, "user_agent", None),
        metadata_json={key: value for key, value in (metadata or {}).items() if key in {"family_revoked", "asset_count", "status"}},
    )
    session.add(event)
    session.commit()
    return event


async def request_context_middleware(request: Request, call_next):
    started = time.perf_counter()
    request_id = uuid4().hex
    incoming = request.headers.get("x-correlation-id", "")
    correlation_id = incoming if SAFE_ID.fullmatch(incoming) else uuid4().hex
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    settings = request.app.state.settings
    content_length = request.headers.get("content-length")
    try:
        request_size = int(content_length) if content_length else 0
    except ValueError:
        request_size = settings.request_size_limit_bytes + 1
    if request_size > settings.request_size_limit_bytes:
        return JSONResponse(
            status_code=413,
            content={"error": {"code": "request_too_large", "message": "Request exceeds the configured limit."}},
        )
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Correlation-ID"] = correlation_id
    request.app.state.metrics.increment("http_requests")
    request.app.state.metrics.observe("http_request_duration_ms", duration_ms)
    if response.status_code >= 400:
        request.app.state.metrics.increment("http_errors")
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "INFO",
        "event_name": "http_request_completed",
        "request_id": request_id,
        "correlation_id": correlation_id,
        "route": request.url.path,
        "method": request.method,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "service": request.app.state.settings.app_name,
        "environment": request.app.state.settings.environment,
    }
    logger.info(json.dumps(record, separators=(",", ":")))
    response.headers.update({
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), geolocation=()",
        "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'",
        "Cache-Control": "no-store" if request.url.path.startswith("/api") else response.headers.get("Cache-Control", "no-cache"),
    })
    return response
