from sqlalchemy import select

from backend.app.core.security import hash_password_reset_token
from backend.app.models import PasswordResetToken, UserAccount


PASSWORD = "StrongPassword123!"


def test_mobile_identity_and_verification_code_recovery(client):
    registration = client.post("/api/v1/auth/register", json={
        "email": "identity@example.com",
        "mobile_number": "98765 43210",
        "password": PASSWORD,
        "display_name": "Identity User",
        "terms_privacy_accepted": True,
    })
    assert registration.status_code == 201
    assert registration.json()["mobile_number"] == "+919876543210"

    by_email = client.post("/api/v1/auth/login", json={"identifier": "identity@example.com", "password": PASSWORD})
    by_mobile = client.post("/api/v1/auth/login", json={"identifier": "+91-98765-43210", "password": PASSWORD})
    assert by_email.status_code == by_mobile.status_code == 200

    requested = client.post("/api/v1/auth/password-reset/request", json={"email": "identity@example.com"})
    unknown = client.post("/api/v1/auth/password-reset/request", json={"email": "unknown@example.com"})
    assert requested.status_code == unknown.status_code == 200
    assert requested.json() == unknown.json()
    code = client.app.state.password_reset_delivery.deliveries[-1]["verification_code"]
    assert len(code) == 6 and code.isdigit()

    with client.app.state.session_factory() as db:
        user = db.scalar(select(UserAccount).where(UserAccount.email == "identity@example.com"))
        reset = db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
        assert reset.token_hash == hash_password_reset_token(f"{user.id}:{code}")
        assert code not in reset.token_hash

    assert client.post("/api/v1/auth/password-reset/validate", json={"email": "identity@example.com", "code": code}).json() == {"valid": True}
    changed = client.post("/api/v1/auth/password-reset/confirm", json={
        "email": "identity@example.com", "code": code, "new_password": "NewStrongPassword456!",
    })
    assert changed.status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "+919876543210", "password": "NewStrongPassword456!"}).status_code == 200
    assert client.post("/api/v1/auth/password-reset/confirm", json={
        "email": "identity@example.com", "code": code, "new_password": "AnotherStrongPassword789!",
    }).status_code == 400


def test_duplicate_mobile_and_attempt_cap(client):
    body = {"email": "first@example.com", "mobile_number": "9876543210", "password": PASSWORD, "display_name": "First", "terms_privacy_accepted": True}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    duplicate = client.post("/api/v1/auth/register", json={**body, "email": "second@example.com", "mobile_number": "+91 98765 43210"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_mobile_number"
    client.post("/api/v1/auth/password-reset/request", json={"email": "first@example.com"})
    for _ in range(5):
        assert client.post("/api/v1/auth/password-reset/validate", json={"email": "first@example.com", "code": "000000"}).status_code == 400
    with client.app.state.session_factory() as db:
        reset = db.scalar(select(PasswordResetToken))
        assert reset.verification_attempts == 5
        assert reset.used_at is not None
