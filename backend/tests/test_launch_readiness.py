from dataclasses import replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from backend.app.commercial.runtime import RuntimeEntitlementService
from backend.app.core.config import Settings
from backend.app.models import (
    AIUsageRecord,
    AITurnAttempt,
    ProviderCallEvent,
    ProgressRecord,
    UserAccount,
)
from backend.app.models.entities import CommercialAuditEvent, CommercialSubscription
from backend.app.usage.service import UsageService


def user_id_for(client, learner) -> str:
    with client.app.state.session_factory() as session:
        return session.scalar(select(UserAccount.id).where(UserAccount.email == learner["email"]))


def verify_founder_account(client, learner) -> None:
    with client.app.state.session_factory() as session:
        account = session.scalar(select(UserAccount).where(UserAccount.email == learner["email"]))
        account.email_verified = True
        session.commit()


def test_launch_config_can_be_disabled_and_remains_test_mode(client):
    response = client.get("/api/v1/launch/config")
    assert response.status_code == 200
    assert response.json()["closed_beta"] is False
    assert response.json()["razorpay_mode"] == "test"
    assert response.json()["provider_policy"] == "OPENAI_FIRST"


def test_feedback_requires_authentication(client):
    response = client.post("/api/v1/launch/feedback", json={"rating": 5, "category": "lesson", "severity": "LOW", "message": "Helpful lesson"})
    assert response.status_code == 401


def test_production_rejects_live_razorpay_mode():
    try:
        Settings(environment="production", database_url="postgresql://db/app", auto_create_tables=False,
                 jwt_secret="x" * 48, force_https=True, secure_cookies=True, cors_origins="https://app.example.com",
                 trusted_hosts="app.example.com", object_storage_backend="s3", object_storage_bucket="private",
                 razorpay_enabled=True, razorpay_webhook_secret="test-secret", razorpay_mode="live", _env_file=None)
    except ValueError as exc:
        assert "razorpay_test_mode" in str(exc)
    else:
        raise AssertionError("live Razorpay mode must fail closed")


def test_subscription_uses_configured_entitlements_and_expires_trial(client, learner):
    configured = replace(
        client.app.state.commercial_service.config,
        free_daily_conversations=7,
        free_daily_voice_minutes=9,
        trial_daily_requests=41,
        premium_voice_minutes=88,
    )
    client.app.state.commercial_service.config = configured

    free = client.get("/api/v1/launch/subscription")
    assert free.status_code == 200
    assert free.json()["entitlements"] == {"daily_conversations": 7, "voice_minutes": 9}

    started = client.post("/api/v1/launch/subscription/trial")
    assert started.status_code == 201
    trial = client.get("/api/v1/launch/subscription").json()
    assert trial["status"] == "TRIAL"
    assert trial["trial_remaining_days"] == client.app.state.settings.commercial_trial_days
    assert trial["entitlements"] == {"daily_conversations": 41, "voice_minutes": 88}
    assert client.post("/api/v1/launch/subscription/trial").status_code == 409

    with client.app.state.session_factory() as session:
        item = session.scalar(select(CommercialSubscription).where(
            CommercialSubscription.learner_id == learner["id"]
        ))
        item.current_period_end = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    expired = client.get("/api/v1/launch/subscription").json()
    assert expired["status"] == "EXPIRED"
    assert expired["trial_remaining_days"] == 0
    assert expired["entitlements"] == {"daily_conversations": 7, "voice_minutes": 9}
    with client.app.state.session_factory() as session:
        assert session.scalar(select(CommercialAuditEvent).where(
            CommercialAuditEvent.action == "TRIAL_EXPIRED"
        )) is not None


def test_past_due_active_subscription_loses_premium_entitlements(client, learner):
    with client.app.state.session_factory() as session:
        session.add(CommercialSubscription(
            learner_id=learner["id"],
            plan_id="PREMIUM_MONTHLY",
            status="ACTIVE",
            provider_id="test",
            current_period_end=datetime.now(UTC) - timedelta(seconds=1),
        ))
        session.commit()

    body = client.get("/api/v1/launch/subscription").json()
    assert body["status"] == "EXPIRED"
    assert body["entitlements"] == {
        "daily_conversations": client.app.state.commercial_service.config.free_daily_conversations,
        "voice_minutes": client.app.state.commercial_service.config.free_daily_voice_minutes,
    }
    with client.app.state.session_factory() as session:
        item = session.scalar(select(CommercialSubscription))
        assert item.status == "EXPIRED"
        assert session.scalar(select(CommercialAuditEvent).where(
            CommercialAuditEvent.action == "SUBSCRIPTION_EXPIRED"
        )) is not None


def test_concurrent_stale_trial_views_emit_one_expiry_audit(client, learner):
    with client.app.state.session_factory() as setup:
        subscription = CommercialSubscription(
            learner_id=learner["id"],
            plan_id="PREMIUM_MONTHLY",
            status="TRIAL",
            provider_id="test",
            trial_started_at=datetime.now(UTC) - timedelta(days=8),
            current_period_end=datetime.now(UTC) - timedelta(days=1),
        )
        setup.add(subscription)
        setup.commit()

    first_session = client.app.state.session_factory()
    second_session = client.app.state.session_factory()
    try:
        # Load stale copies before either resolver performs the conditional update.
        first_session.scalar(select(CommercialSubscription))
        second_session.scalar(select(CommercialSubscription))
        first = RuntimeEntitlementService(
            first_session,
            client.app.state.commercial_service.config,
        ).view(learner["id"], payment_mode="test")
        second = RuntimeEntitlementService(
            second_session,
            client.app.state.commercial_service.config,
        ).view(learner["id"], payment_mode="test")
        assert first["status"] == second["status"] == "EXPIRED"
    finally:
        first_session.close()
        second_session.close()

    with client.app.state.session_factory() as verification:
        item = verification.scalar(select(CommercialSubscription))
        assert item.status == "EXPIRED"
        assert item.version == 2
        assert verification.scalar(select(func.count()).select_from(CommercialAuditEvent).where(
            CommercialAuditEvent.action == "TRIAL_EXPIRED"
        )) == 1


def test_test_mode_upgrade_is_only_an_audited_preview(client, learner):
    response = client.post("/api/v1/launch/subscription/upgrade")
    assert response.status_code == 202
    assert response.json() == {
        "status": "UPGRADE_PREVIEW",
        "payment_mode": "test",
        "real_charge": False,
    }
    with client.app.state.session_factory() as session:
        assert session.scalar(select(CommercialSubscription)) is None
        event = session.scalar(select(CommercialAuditEvent).where(
            CommercialAuditEvent.action == "TEST_UPGRADE_PREVIEWED"
        ))
        assert event is not None
        assert event.learner_id == learner["id"]


def test_free_daily_conversation_limit_is_enforced_server_side(client, learner):
    client.app.state.commercial_service.config = replace(
        client.app.state.commercial_service.config,
        free_daily_conversations=1,
    )
    payload = {"learner_id": learner["id"], "scenario_id": "daily-conversation"}
    assert client.post("/api/v1/conversations", json=payload).status_code == 201
    limited = client.post("/api/v1/conversations", json=payload)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "daily_conversation_limit_reached"


def test_voice_allowance_is_enforced_before_provider_work(client, learner, conversation):
    with client.app.state.session_factory() as session:
        session.add(ProviderCallEvent(
            learner_id=learner["id"],
            user_id=user_id_for(client, learner),
            operation_kind="stt",
            attempt_reference="used-voice-allowance",
            duration_ms=(
                client.app.state.commercial_service.config.free_daily_voice_minutes * 60_000
            ),
            request_count=1,
            outcome="SUCCESS",
        ))
        session.commit()
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/transcriptions",
        content=b"bounded-audio",
        headers={
            "Content-Type": "audio/webm",
            "X-Audio-Duration-Ms": "1000",
            "X-Voice-Processing-Consent": "accepted",
        },
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "daily_voice_limit_reached"


def test_ai_request_entitlement_is_enforced_before_turn_attempt(client, learner, conversation):
    limit = client.app.state.commercial_service.config.free_daily_conversations
    with client.app.state.session_factory() as session:
        session.add_all([
            AITurnAttempt(
                conversation_id=conversation["id"],
                learner_id=learner["id"],
                idempotency_key=f"commercial-used-{index}",
                learner_text="Counted tutor request.",
                status="FAILED_FINAL",
                failure_code="provider_unavailable",
            )
            for index in range(limit)
        ])
        session.commit()
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/ai-turns",
        json={"message": "I am ready to practise.", "input_source": "TEXT"},
        headers={"Idempotency-Key": "commercial-limit-turn"},
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "daily_ai_request_limit_reached"


def test_opening_turn_does_not_consume_learner_ai_request_allowance(client, learner, conversation):
    configured = replace(
        client.app.state.commercial_service.config,
        free_daily_conversations=1,
    )
    with client.app.state.session_factory() as session:
        RuntimeEntitlementService(session, configured).enforce_ai_request(learner["id"])


def test_supporting_provider_usage_does_not_double_count_tutor_turn_allowance(client, learner):
    learner_id = learner["id"]
    user_id = user_id_for(client, learner)
    limit = client.app.state.commercial_service.config.free_daily_conversations
    with client.app.state.session_factory() as session:
        session.add_all([
            AIUsageRecord(
                learner_id=learner_id,
                user_id=user_id,
                provider_kind=provider_kind,
                request_count=limit,
            )
            for provider_kind in ("language_review", "stt")
        ])
        session.commit()
        RuntimeEntitlementService(
            session,
            client.app.state.commercial_service.config,
        ).enforce_ai_request(learner_id)
        UsageService(session).enforce(learner_id, user_id)


def test_progress_reports_verified_streak_activity_and_achievements(client, learner, conversation):
    today = datetime.now(UTC).date()
    with client.app.state.session_factory() as session:
        for offset in range(3):
            session.add(ProgressRecord(
                learner_id=learner["id"],
                lesson_id=f"verified-lesson-{offset}",
                practice_date=today - timedelta(days=offset),
                duration_seconds=300,
                score=80,
            ))
        session.commit()

    result = client.get("/api/v1/launch/progress")
    assert result.status_code == 200
    body = result.json()
    assert body["completed_lessons"] == 3
    assert body["daily_streak"] == 3
    assert body["weekly_activity"] == 3
    assert body["monthly_activity"] >= 1
    assert body["recent_achievements"] == [
        "Completed first lesson",
        "Built a 3-day practice streak",
        "Started first conversation",
    ]
    assert body["conversation_history_summary"] == {
        "conversations": 1,
        "recent_sessions": 1,
    }


def test_empty_progress_does_not_invent_achievements(client, learner):
    result = client.get("/api/v1/launch/progress")
    assert result.status_code == 200
    assert result.json()["daily_streak"] == 0
    assert result.json()["recent_achievements"] == []


def test_founder_dashboard_uses_all_daily_registrations_and_configured_prices(client, learner):
    client.app.state.settings.founder_emails = "learner@example.com"
    client.app.state.settings.commercial_monthly_price_inr = 777
    verify_founder_account(client, learner)
    with client.app.state.session_factory() as session:
        session.add_all([
            UserAccount(
                email=f"founder-metric-{index}@example.com",
                password_hash="not-used-in-dashboard-test",
                status="ACTIVE",
            )
            for index in range(11)
        ])
        session.add(CommercialSubscription(
            learner_id=learner["id"],
            plan_id="PREMIUM_MONTHLY",
            status="ACTIVE",
            provider_id="test",
            current_period_end=datetime.now(UTC) + timedelta(days=30),
        ))
        session.commit()

    dashboard = client.get("/api/v1/launch/founder-dashboard")
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["daily_registrations"] == 12
    assert len(body["recent_registrations"]) == 10
    assert body["estimated_mrr_inr"] == 777
    assert body["health"] == "CHECK_HEALTH_READY"
    assert body["health_endpoint"] == "/health/ready"


def test_founder_dashboard_is_read_only_while_reporting_stale_trial_as_expired(client, learner):
    client.app.state.settings.founder_emails = "learner@example.com"
    verify_founder_account(client, learner)
    with client.app.state.session_factory() as session:
        session.add(CommercialSubscription(
            learner_id=learner["id"],
            plan_id="PREMIUM_MONTHLY",
            status="TRIAL",
            provider_id="test",
            trial_started_at=datetime.now(UTC) - timedelta(days=8),
            current_period_end=datetime.now(UTC) - timedelta(days=1),
        ))
        session.commit()

    body = client.get("/api/v1/launch/founder-dashboard").json()
    assert body["read_only"] is True
    assert body["trials"] == 0
    assert body["subscription_overview"] == {"EXPIRED": 1}
    with client.app.state.session_factory() as session:
        item = session.scalar(select(CommercialSubscription))
        assert item.status == "TRIAL"
        assert session.scalar(select(CommercialAuditEvent).where(
            CommercialAuditEvent.action == "TRIAL_EXPIRED"
        )) is None


def test_founder_dashboard_does_not_count_past_due_active_subscription(client, learner):
    client.app.state.settings.founder_emails = "learner@example.com"
    verify_founder_account(client, learner)
    with client.app.state.session_factory() as session:
        session.add(CommercialSubscription(
            learner_id=learner["id"],
            plan_id="PREMIUM_MONTHLY",
            status="ACTIVE",
            provider_id="test",
            current_period_end=datetime.now(UTC) - timedelta(days=1),
        ))
        session.commit()

    body = client.get("/api/v1/launch/founder-dashboard").json()
    assert body["paid_users"] == 0
    assert body["estimated_mrr_inr"] == 0
    assert body["subscription_overview"] == {"EXPIRED": 1}
    with client.app.state.session_factory() as session:
        assert session.scalar(select(CommercialSubscription)).status == "ACTIVE"


def test_unverified_configured_email_cannot_claim_founder_dashboard(client, learner):
    client.app.state.settings.founder_emails = learner["email"]
    response = client.get("/api/v1/launch/founder-dashboard")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "founder_access_required"
