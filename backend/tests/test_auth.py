from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from backend.app.core.errors import AppError
from backend.app.core.security import hash_refresh_token, verify_password
from backend.app.models import Learner, PasswordResetToken, RefreshToken, SecurityAuditEvent, UserAccount


PASSWORD = "StrongPassword123!"


def register(client, email="USER@Example.COM", password=PASSWORD, name="User"):
    return client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "display_name": name, "terms_privacy_accepted": True,
    })


def test_registration_normalises_email_and_hides_secrets(client):
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@example.com"
    assert "password" not in str(body).lower()
    assert body["tokens"]["access_token"]
    with client.app.state.session_factory() as db:
        account = db.scalar(select(UserAccount))
        learner = db.scalar(select(Learner))
        assert account.password_hash != PASSWORD
        assert learner.user_account_id == account.id


def test_duplicate_email_and_weak_password(client):
    assert register(client).status_code == 201
    duplicate = register(client, "USER@example.com")
    assert duplicate.status_code == 409
    weak = register(client, "other@example.com", "short")
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "weak_password"
    too_long_value = "é" * 40
    too_long = register(client, "long@example.com", too_long_value)
    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "password_too_long"
    assert too_long_value not in too_long.text


def test_registration_requires_terms_and_privacy_consent(client):
    response = client.post("/api/v1/auth/register", json={
        "email": "no-consent@example.com", "password": PASSWORD,
        "display_name": "No Consent", "terms_privacy_accepted": False,
    })
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "legal_consent_required"
    with client.app.state.session_factory() as db:
        assert db.scalar(select(UserAccount).where(UserAccount.email == "no-consent@example.com")) is None


def test_failed_token_creation_rolls_back_registration_and_allows_clean_retry(client, monkeypatch):
    """Regresses: failed registration -> duplicate account -> login failure."""
    from backend.app.services import auth as auth_service

    real_create_access_token = auth_service.create_access_token

    def fail_token_creation(*_args, **_kwargs):
        raise AppError(503, "authentication_unavailable", "Authentication signing is not configured.")

    monkeypatch.setattr(auth_service, "create_access_token", fail_token_creation)
    first = register(client, "atomic-registration@example.com")
    assert first.status_code == 503

    with client.app.state.session_factory() as db:
        assert db.scalar(select(UserAccount).where(UserAccount.email == "atomic-registration@example.com")) is None
        assert db.scalar(select(Learner).where(Learner.email == "atomic-registration@example.com")) is None
        assert db.scalar(select(RefreshToken).join(UserAccount).where(
            UserAccount.email == "atomic-registration@example.com"
        )) is None

    monkeypatch.setattr(auth_service, "create_access_token", real_create_access_token)
    retry = register(client, "atomic-registration@example.com")
    assert retry.status_code == 201
    login = client.post("/api/v1/auth/login", json={
        "email": "atomic-registration@example.com", "password": PASSWORD,
    })
    assert login.status_code == 200


def test_login_success_invalid_credentials_and_disabled_account(client):
    register(client)
    good = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": PASSWORD})
    assert good.status_code == 200
    invalid = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong-password"})
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "invalid_credentials"
    with client.app.state.session_factory() as db:
        account = db.scalar(select(UserAccount))
        account.status = "DISABLED"
        db.commit()
    disabled = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": PASSWORD})
    assert disabled.status_code == 401
    assert disabled.json()["error"]["code"] == "invalid_credentials"


def _request_reset(client, email="user@example.com"):
    response = client.post("/api/v1/auth/password-reset/request", json={"email": email})
    deliveries = client.app.state.password_reset_delivery.deliveries
    reset_url = deliveries[-1]["reset_url"] if deliveries else ""
    token = reset_url.split("token=", 1)[1] if "token=" in reset_url else ""
    return response, token


def test_password_reset_is_neutral_single_use_and_revokes_sessions(client, caplog):
    registered = register(client).json()
    original_refresh = registered["tokens"]["refresh_token"]
    neutral, raw_token = _request_reset(client)
    unknown, _ = _request_reset(client, "unknown@example.com")
    assert neutral.status_code == unknown.status_code == 200
    assert neutral.json() == unknown.json()
    assert raw_token and len(raw_token) >= 32

    with client.app.state.session_factory() as db:
        reset = db.scalar(select(PasswordResetToken))
        assert reset.token_hash != raw_token
        assert raw_token not in reset.token_hash
        account = db.scalar(select(UserAccount).where(UserAccount.email == "user@example.com"))
        assert verify_password(PASSWORD, account.password_hash)

    assert client.post("/api/v1/auth/password-reset/validate", json={"token": raw_token}).json() == {"valid": True}
    new_password = "NewStrongPassword456!"
    changed = client.post("/api/v1/auth/password-reset/confirm", json={
        "token": raw_token, "new_password": new_password,
    })
    assert changed.status_code == 200
    assert client.post("/api/v1/auth/login", json={
        "email": "user@example.com", "password": PASSWORD,
    }).status_code == 401
    assert client.post("/api/v1/auth/login", json={
        "email": "user@example.com", "password": new_password,
    }).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": original_refresh}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {registered['tokens']['access_token']}"
    }).status_code == 401
    reused = client.post("/api/v1/auth/password-reset/confirm", json={
        "token": raw_token, "new_password": "AnotherStrongPassword789!",
    })
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "used_reset_token"
    with client.app.state.session_factory() as db:
        reset = db.scalar(select(PasswordResetToken))
        assert reset.used_at is not None
        audit = db.scalar(select(SecurityAuditEvent).where(
            SecurityAuditEvent.event_type == "PASSWORD_RESET_COMPLETED"
        ))
        assert audit is not None
    assert raw_token not in caplog.text
    assert PASSWORD not in caplog.text
    assert new_password not in caplog.text


def test_password_reset_rejects_invalid_expired_and_weak_tokens(client):
    register(client)
    _, raw_token = _request_reset(client)
    invalid = client.post("/api/v1/auth/password-reset/validate", json={"token": "x" * 48})
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "invalid_reset_token"
    weak = client.post("/api/v1/auth/password-reset/confirm", json={
        "token": raw_token, "new_password": "short",
    })
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "weak_password"
    with client.app.state.session_factory() as db:
        reset = db.scalar(select(PasswordResetToken))
        reset.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    expired = client.post("/api/v1/auth/password-reset/validate", json={"token": raw_token})
    assert expired.status_code == 400
    assert expired.json()["error"]["code"] == "expired_reset_token"


def test_password_reset_requests_are_rate_limited_per_email(client):
    register(client)
    for _ in range(3):
        assert client.post("/api/v1/auth/password-reset/request", json={
            "email": "user@example.com"
        }).status_code == 200
    limited = client.post("/api/v1/auth/password-reset/request", json={
        "email": "user@example.com"
    })
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"


def test_password_reset_delivery_failure_remains_neutral_and_disables_token(client):
    from backend.app.providers.password_reset import DisabledPasswordResetDelivery

    register(client)
    client.app.state.password_reset_delivery = DisabledPasswordResetDelivery()
    known = client.post("/api/v1/auth/password-reset/request", json={"email": "user@example.com"})
    unknown = client.post("/api/v1/auth/password-reset/request", json={"email": "unknown@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    with client.app.state.session_factory() as db:
        reset = db.scalar(select(PasswordResetToken))
        assert reset.used_at is not None
        failed = db.scalar(select(SecurityAuditEvent).where(
            SecurityAuditEvent.event_type == "PASSWORD_RESET_DELIVERY_FAILED"
        ))
        assert failed.outcome == "FAILED"


def test_password_reset_rolls_back_password_token_and_session_revocation(client, monkeypatch):
    from backend.app.services import auth as auth_service

    registered = register(client).json()
    raw_refresh = registered["tokens"]["refresh_token"]
    _, raw_token = _request_reset(client)

    def fail_hashing(_password):
        raise RuntimeError("injected hashing failure")

    monkeypatch.setattr(auth_service, "hash_password", fail_hashing)
    try:
        client.post("/api/v1/auth/password-reset/confirm", json={
            "token": raw_token, "new_password": "NewStrongPassword456!",
        })
    except RuntimeError:
        pass
    with client.app.state.session_factory() as db:
        reset = db.scalar(select(PasswordResetToken))
        refresh = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_refresh)))
        account = db.scalar(select(UserAccount).where(UserAccount.email == "user@example.com"))
        assert reset.used_at is None
        assert refresh.revoked_at is None
        assert verify_password(PASSWORD, account.password_hash)


def test_me_and_anonymous_rejection(client):
    body = register(client).json()
    anonymous = client.get(f"/api/v1/learners/{body['learner_id']}")
    assert anonymous.status_code == 401
    client.headers["Authorization"] = f"Bearer {body['tokens']['access_token']}"
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["learner_id"] == body["learner_id"]
    assert "password_hash" not in me.json()


def test_access_token_wrong_issuer_audience_and_expired(client):
    body = register(client).json()
    settings = client.app.state.settings
    now = datetime.now(timezone.utc)
    base = {"sub": body["id"], "type": "access", "sev": 0, "iat": now, "exp": now + timedelta(minutes=5)}
    cases = [
        {**base, "iss": "wrong", "aud": settings.jwt_audience},
        {**base, "iss": settings.jwt_issuer, "aud": "wrong"},
        {**base, "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "exp": now - timedelta(seconds=1)},
    ]
    for claims in cases:
        token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
    unexpected_algorithm = jwt.encode(
        {**base, "iss": settings.jwt_issuer, "aud": settings.jwt_audience},
        settings.jwt_secret,
        algorithm="HS384",
    )
    assert client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {unexpected_algorithm}"}
    ).status_code == 401
    none_token = jwt.encode(
        {**base, "iss": settings.jwt_issuer, "aud": settings.jwt_audience},
        key="",
        algorithm="none",
    )
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {none_token}"}).status_code == 401


def test_refresh_rotation_reuse_logout_and_logout_all(client):
    body = register(client).json()
    first = body["tokens"]["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200
    second = rotated.json()["refresh_token"]
    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "refresh_token_reused"
    with client.app.state.session_factory() as db:
        family = list(db.scalars(select(RefreshToken).order_by(RefreshToken.issued_at)))
        assert len({token.family_id for token in family}) == 1
        assert family[1].parent_token_id == family[0].id
        assert family[1].revoked_at is not None
        audit = db.scalar(select(SecurityAuditEvent).where(
            SecurityAuditEvent.event_type == "REFRESH_TOKEN_REUSE_DETECTED"
        ))
        assert audit.event_type == "REFRESH_TOKEN_REUSE_DETECTED"
        assert audit.metadata_json == {"family_revoked": True}
    access = rotated.json()["access_token"]
    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": second},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert logout.status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second}).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": PASSWORD}).json()
    client.post("/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {login['access_token']}"})
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}).status_code == 401
    with client.app.state.session_factory() as db:
        assert db.scalar(select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(login["refresh_token"])
        )).revoked_at is not None


def test_locked_and_deleted_accounts_cannot_authenticate(client):
    for index, account_status in enumerate(("LOCKED", "DELETED")):
        email = f"status-{index}@example.com"
        registered = register(client, email).json()
        with client.app.state.session_factory() as db:
            account = db.get(UserAccount, registered["id"])
            account.status = account_status
            db.commit()
        assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
        assert client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {registered['tokens']['access_token']}"},
        ).status_code == 401
        assert client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": registered["tokens"]["refresh_token"]},
        ).status_code == 401


def test_login_network_throttle_is_privacy_safe(client):
    for index in range(client.app.state.settings.login_attempt_limit):
        response = client.post("/api/v1/auth/login", json={
            "email": f"unknown-{index}@example.com", "password": "wrong-password",
        })
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"
    throttled = client.post("/api/v1/auth/login", json={
        "email": "another-unknown@example.com", "password": "wrong-password",
    })
    assert throttled.status_code == 429
    assert throttled.json()["error"]["code"] == "login_throttled"


def test_cross_user_ownership_is_privacy_safe_404(client):
    first = register(client, "first@example.com", name="First").json()
    second = register(client, "second@example.com", name="Second").json()
    response = client.get(
        f"/api/v1/learners/{first['learner_id']}",
        headers={"Authorization": f"Bearer {second['tokens']['access_token']}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


def test_conversation_lesson_voice_and_audio_ownership(client):
    first = register(client, "owner@example.com", name="Owner").json()
    owner_headers = {"Authorization": f"Bearer {first['tokens']['access_token']}"}
    learner_id = first["learner_id"]
    conversation = client.post("/api/v1/conversations", json={
        "learner_id": learner_id, "scenario_id": "daily-conversation",
    }, headers=owner_headers).json()
    lesson = client.post("/api/v1/lesson-sessions", json={
        "learner_id": learner_id, "lesson_id": "starter-introductions",
        "conversation_id": conversation["id"],
    }, headers=owner_headers).json()
    client.put(f"/api/v1/learners/{learner_id}/voice-consent", json={
        "voice_processing_consent": True,
        "audio_storage_consent": False,
        "consent_version": "ownership-test",
    }, headers=owner_headers)
    voice = client.post("/api/v1/voice-sessions", json={
        "learner_id": learner_id, "scenario_id": "daily-conversation",
    }, headers=owner_headers).json()
    client.post(f"/api/v1/voice-sessions/{voice['id']}/turns", json={
        "simulated_audio_reference": "ownership/audio.wav",
        "fake_transcript": "Hello.",
        "media_type": "audio/wav",
    }, headers=owner_headers)

    second = register(client, "intruder@example.com", name="Intruder").json()
    intruder_headers = {"Authorization": f"Bearer {second['tokens']['access_token']}"}
    endpoints = [
        f"/api/v1/conversations/{conversation['id']}",
        f"/api/v1/lesson-sessions/{lesson['id']}",
        f"/api/v1/voice-sessions/{voice['id']}",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint, headers=intruder_headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"
