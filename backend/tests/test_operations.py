import json
import logging
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.core.config import Settings
from backend.app.core.operations import InMemoryMetrics, InMemoryRateLimiter, RateLimitPolicy
from backend.app.main import create_app
from backend.app.models import AudioAsset, SecurityAuditEvent, UserAccount
from backend.app.services.admin import AdministrativeService
from backend.app.services.voice import VoiceService


def test_request_and_correlation_ids(client):
    generated = client.get("/health/live", headers={"X-Correlation-ID": "bad value!"})
    assert len(generated.headers["X-Request-ID"]) == 32
    assert generated.headers["X-Correlation-ID"] != "bad value!"
    propagated = client.get("/health/live", headers={"X-Correlation-ID": "incident-123"})
    assert propagated.headers["X-Correlation-ID"] == "incident-123"


def test_structured_logs_do_not_contain_credentials(client, caplog):
    caplog.set_level(logging.INFO, logger="spoken_english.operations")
    secret = "not-a-real-access-token"
    client.get("/health/live", headers={"Authorization": f"Bearer {secret}"})
    records = [record.message for record in caplog.records if record.name == "spoken_english.operations"]
    payload = json.loads(records[-1])
    assert payload["event_name"] == "http_request_completed"
    assert payload["request_id"]
    assert secret not in records[-1]
    assert "authorization" not in records[-1].lower()


def test_health_readiness_version_and_missing_secret(client):
    assert client.get("/health/live").status_code == 200
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {
        "database": "ready",
        "migration": "development_metadata",
        "authentication": "ready",
        "providers": "configured",
    }
    version = client.get("/health/version").json()
    assert version["api_version"] == "v1"
    assert "secret" not in str(version).lower()

    app = create_app(Settings(
        database_url="sqlite:///:memory:",
        environment="production",
        jwt_secret="",
        auto_create_tables=True,
        _env_file=None,
    ))
    with TestClient(app) as production:
        response = production.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["authentication"] == "unavailable"
    app.state.engine.dispose()


def test_readiness_rejects_unconfigured_provider():
    app = create_app(Settings(
        database_url="sqlite:///:memory:",
        environment="production",
        jwt_secret="test-signing-secret-at-least-32-bytes-long",
        llm_provider="external-not-configured",
        auto_create_tables=True,
        _env_file=None,
    ))
    with TestClient(app) as production:
        response = production.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["providers"] == "unavailable"
    app.state.engine.dispose()


def test_metrics_and_rate_limit_decisions():
    metrics = InMemoryMetrics()
    metrics.increment("requests")
    metrics.observe("duration", 1.5)
    metrics.gauge("active", 2)
    assert metrics.snapshot() == {
        "counters": {"requests": 1},
        "observations": {"duration": [1.5]},
        "gauges": {"active": 2},
    }
    now = [0.0]
    limiter = InMemoryRateLimiter(lambda: now[0])
    policy = RateLimitPolicy("test", 1, 10)
    assert limiter.decide(policy, "privacy-key").allowed
    denied = limiter.decide(policy, "privacy-key")
    assert denied.allowed is False and denied.retry_after == 10
    now[0] = 11
    assert limiter.decide(policy, "privacy-key").allowed


def test_retry_after_response(client):
    policy = RateLimitPolicy("registration", 0, 17)
    from backend.app.core import operations
    original = operations.RATE_POLICIES["registration"]
    operations.RATE_POLICIES["registration"] = policy
    try:
        response = client.post("/api/v1/auth/register", json={
            "email": "limited@example.com", "password": "StrongPassword123!", "display_name": "Limited",
        })
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "17"
        assert response.json()["error"]["code"] == "rate_limited"
    finally:
        operations.RATE_POLICIES["registration"] = original


def test_signing_key_rotation_and_unknown_key(client):
    settings = client.app.state.settings
    settings.jwt_active_key_id = "current"
    settings.jwt_verification_keys_json = json.dumps({
        "current": "current-signing-secret-at-least-32-bytes",
        "previous": "previous-signing-secret-at-least-32-bytes",
    })
    registration = client.post("/api/v1/auth/register", json={
        "email": "keys@example.com", "password": "StrongPassword123!", "display_name": "Keys",
    }).json()
    header = jwt.get_unverified_header(registration["tokens"]["access_token"])
    assert header["kid"] == "current"
    now = datetime.now(timezone.utc)
    claims = {
        "sub": registration["id"], "type": "access", "iat": now,
        "exp": now + timedelta(minutes=5), "iss": settings.jwt_issuer, "aud": settings.jwt_audience,
    }
    previous = jwt.encode(
        claims,
        json.loads(settings.jwt_verification_keys_json)["previous"],
        algorithm=settings.jwt_algorithm,
        headers={"kid": "previous"},
    )
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {previous}"}).status_code == 200
    unknown = jwt.encode(
        claims,
        "unknown-signing-secret-at-least-32-bytes",
        algorithm=settings.jwt_algorithm,
        headers={"kid": "unknown"},
    )
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {unknown}"}).status_code == 401


def test_signing_key_configuration_rejects_duplicates_and_missing_active_key():
    duplicate = Settings(
        jwt_active_key_id="same",
        jwt_verification_keys_json='{"same":"first-secret-at-least-32-bytes-long","same":"second-secret-at-least-32-bytes-long"}',
        _env_file=None,
    )
    with pytest.raises(ValueError, match="Duplicate"):
        duplicate.signing_keys()
    missing = Settings(
        jwt_active_key_id="current",
        jwt_verification_keys_json='{"previous":"previous-secret-at-least-32-bytes-long"}',
        _env_file=None,
    )
    with pytest.raises(ValueError, match="Active"):
        missing.signing_keys()


def test_auth_audits_and_admin_boundary(client):
    registered = client.post("/api/v1/auth/register", json={
        "email": "audit@example.com", "password": "StrongPassword123!", "display_name": "Audit",
    }).json()
    client.post("/api/v1/auth/login", json={"email": "audit@example.com", "password": "wrong"})
    client.post("/api/v1/auth/login", json={"email": "audit@example.com", "password": "StrongPassword123!"})
    with client.app.state.session_factory() as db:
        events = list(db.scalars(select(SecurityAuditEvent).order_by(SecurityAuditEvent.occurred_at)))
        assert {"ACCOUNT_REGISTERED", "LOGIN_FAILED", "LOGIN_SUCCEEDED"} <= {event.event_type for event in events}
        admin = AdministrativeService(db)
        admin.set_account_status(registered["id"], "LOCKED")
        assert db.get(UserAccount, registered["id"]).status == "LOCKED"
    paths = {route.path for route in client.app.routes}
    assert all(not path.startswith("/api/v1/admin") for path in paths)


def test_security_audit_events_are_append_only(client):
    client.post("/api/v1/auth/register", json={
        "email": "append-only@example.com",
        "password": "StrongPassword123!",
        "display_name": "Append Only",
    })
    with client.app.state.session_factory() as db:
        event = db.scalar(select(SecurityAuditEvent))
        event.outcome = "ALTERED"
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
        db.rollback()
        event = db.scalar(select(SecurityAuditEvent))
        db.delete(event)
        with pytest.raises(ValueError, match="append-only"):
            db.commit()


def test_cleanup_batches_and_idempotence(client, learner):
    from backend.tests.test_voice import add_turn, create_voice_session, set_consent
    set_consent(client, learner)
    session_id = create_voice_session(client, learner).json()["id"]
    add_turn(client, session_id, key="cleanup/one.wav")
    add_turn(client, session_id, key="cleanup/two.wav")
    now = datetime.now(timezone.utc)
    with client.app.state.session_factory() as db:
        for asset in db.scalars(select(AudioAsset)):
            asset.expires_at = now - timedelta(hours=1)
        db.commit()
        service = VoiceService(db)
        assert service.cleanup(now, batch_size=1) == 1
        assert service.cleanup(now, batch_size=1) == 1
        assert service.cleanup(now, batch_size=1) == 0
        assets = list(db.scalars(select(AudioAsset)))
        assert all(asset.deletion_confirmed_at is not None for asset in assets)
        assert all(asset.cleanup_retry_count == 0 for asset in assets)
