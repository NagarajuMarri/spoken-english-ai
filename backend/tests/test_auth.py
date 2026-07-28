from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from backend.app.core.security import hash_refresh_token
from backend.app.models import Learner, RefreshToken, UserAccount


PASSWORD = "StrongPassword123!"


def register(client, email="USER@Example.COM", password=PASSWORD, name="User"):
    return client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "display_name": name,
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
    base = {"sub": body["id"], "type": "access", "iat": now, "exp": now + timedelta(minutes=5)}
    cases = [
        {**base, "iss": "wrong", "aud": settings.jwt_audience},
        {**base, "iss": settings.jwt_issuer, "aud": "wrong"},
        {**base, "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "exp": now - timedelta(seconds=1)},
    ]
    for claims in cases:
        token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_refresh_rotation_reuse_logout_and_logout_all(client):
    body = register(client).json()
    first = body["tokens"]["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200
    second = rotated.json()["refresh_token"]
    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "refresh_token_reused"
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
