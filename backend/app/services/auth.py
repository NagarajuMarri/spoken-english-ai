from datetime import timedelta
import secrets

from fastapi import Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    normalize_email,
    utc_now,
    verify_password,
)
from backend.app.models import Learner, RefreshToken, UserAccount


class AuthService:
    def __init__(self, session: Session, request: Request) -> None:
        self.session = session
        self.request = request
        self.settings = request.app.state.settings

    def _pair(self, user: UserAccount, previous: RefreshToken | None = None) -> dict:
        now = utc_now()
        raw = secrets.token_urlsafe(48)
        token = RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw),
            issued_at=now,
            expires_at=now + timedelta(days=self.settings.refresh_token_lifetime_days),
            user_agent=(self.request.headers.get("user-agent") or "")[:200] or None,
            ip_metadata=None,
        )
        self.session.add(token)
        self.session.flush()
        if previous is not None:
            previous.revoked_at = now
            previous.replaced_by_token_id = token.id
        self.session.commit()
        return {
            "access_token": create_access_token(self.settings, user.id, now),
            "refresh_token": raw,
            "token_type": "bearer",
            "expires_in": self.settings.access_token_lifetime_minutes * 60,
        }

    def register(self, data):
        email = normalize_email(str(data.email))
        if len(data.password) < self.settings.password_minimum_length:
            raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "weak_password", "Password does not meet requirements.")
        user = UserAccount(email=email, password_hash=hash_password(data.password))
        try:
            self.session.add(user)
            self.session.flush()
            learner = Learner(email=email, display_name=data.display_name.strip(), user_account_id=user.id)
            self.session.add(learner)
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError(status.HTTP_409_CONFLICT, "duplicate_email", "An account with this email exists.") from exc
        tokens = self._pair(user)
        return self.account_payload(user, learner, tokens)

    def login(self, data):
        email = normalize_email(str(data.email))
        key = hashlib_key(email)
        throttler = self.request.app.state.login_throttler
        throttler.check(key)
        user = self.session.scalar(select(UserAccount).where(UserAccount.email == email))
        if user is None or user.status != "ACTIVE" or not verify_password(data.password, user.password_hash):
            throttler.failed(key)
            raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_credentials", "Invalid email or password.")
        throttler.succeeded(key)
        user.last_login_at = utc_now()
        self.session.commit()
        return self._pair(user)

    def refresh(self, raw: str):
        token = self.session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)))
        now = utc_now()
        if token is None:
            raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_refresh_token", "Invalid refresh token.")
        if token.revoked_at is not None:
            raise AppError(status.HTTP_401_UNAUTHORIZED, "refresh_token_reused", "Refresh token has already been used.")
        if token.expires_at.replace(tzinfo=token.expires_at.tzinfo or now.tzinfo) <= now:
            raise AppError(status.HTTP_401_UNAUTHORIZED, "refresh_token_expired", "Refresh token expired.")
        user = self.session.get(UserAccount, token.user_id)
        if user is None or user.status != "ACTIVE":
            raise AppError(status.HTTP_401_UNAUTHORIZED, "account_unavailable", "Account is unavailable.")
        return self._pair(user, token)

    def logout(self, raw: str, user_id: str):
        token = self.session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)))
        if token is not None and token.user_id == user_id and token.revoked_at is None:
            token.revoked_at = utc_now()
            self.session.commit()

    def logout_all(self, user_id: str):
        now = utc_now()
        tokens = self.session.scalars(
            select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        )
        for token in tokens:
            token.revoked_at = now
        self.session.commit()

    @staticmethod
    def account_payload(user, learner, tokens=None):
        payload = {
            "id": user.id,
            "email": user.email,
            "status": user.status,
            "email_verified": user.email_verified,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "last_login_at": user.last_login_at,
            "learner_id": learner.id,
        }
        if tokens is not None:
            payload["tokens"] = tokens
        return payload


def hashlib_key(email: str) -> str:
    import hashlib
    return hashlib.sha256(email.encode()).hexdigest()
