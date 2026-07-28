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
    privacy_minimised_network_key,
    utc_now,
    verify_password,
)
from backend.app.models import Learner, RefreshToken, SecurityAuditEvent, UserAccount
from backend.app.models.entities import new_id


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
            family_id=previous.family_id if previous is not None else new_id(),
            parent_token_id=previous.id if previous is not None else None,
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
        if len(data.password.encode("utf-8")) > self.settings.password_maximum_bytes:
            raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "password_too_long", "Password does not meet requirements.")
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
        keys = (hashlib_key(email), privacy_minimised_network_key(self.request))
        throttler = self.request.app.state.login_throttler
        for key in keys:
            throttler.check(key)
        user = self.session.scalar(select(UserAccount).where(UserAccount.email == email))
        if user is None or user.status != "ACTIVE" or not verify_password(data.password, user.password_hash):
            for key in keys:
                throttler.failed(key)
            raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_credentials", "Invalid email or password.")
        for key in keys:
            throttler.succeeded(key)
        user.last_login_at = utc_now()
        self.session.commit()
        return self._pair(user)

    def refresh(self, raw: str):
        token = self.session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(raw))
            .with_for_update()
        )
        now = utc_now()
        if token is None:
            raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_refresh_token", "Invalid refresh token.")
        if token.revoked_at is not None:
            if token.replaced_by_token_id is not None:
                self._revoke_family_for_reuse(token, now)
            raise AppError(status.HTTP_401_UNAUTHORIZED, "refresh_token_reused", "Refresh token has already been used.")
        if token.expires_at.replace(tzinfo=token.expires_at.tzinfo or now.tzinfo) <= now:
            raise AppError(status.HTTP_401_UNAUTHORIZED, "refresh_token_expired", "Refresh token expired.")
        user = self.session.get(UserAccount, token.user_id)
        if user is None or user.status != "ACTIVE":
            raise AppError(status.HTTP_401_UNAUTHORIZED, "account_unavailable", "Account is unavailable.")
        try:
            return self._pair(user, token)
        except IntegrityError:
            self.session.rollback()
            token = self.session.scalar(
                select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)).with_for_update()
            )
            if token is not None:
                self._revoke_family_for_reuse(token, utc_now())
            raise AppError(
                status.HTTP_401_UNAUTHORIZED,
                "refresh_token_reused",
                "Refresh token has already been used.",
            )

    def _revoke_family_for_reuse(self, token: RefreshToken, now) -> None:
        family = list(self.session.scalars(
            select(RefreshToken).where(RefreshToken.family_id == token.family_id).with_for_update()
        ))
        for member in family:
            if member.revoked_at is None:
                member.revoked_at = now
        self.session.add(SecurityAuditEvent(
            event_type="REFRESH_TOKEN_REUSE_DETECTED",
            user_id=token.user_id,
            occurred_at=now,
            outcome="BLOCKED",
            reason_code="refresh_token_reused",
            privacy_minimised_network_key=privacy_minimised_network_key(self.request),
            user_agent_summary=(self.request.headers.get("user-agent") or "")[:100] or None,
            metadata_json={"family_revoked": True},
        ))
        self.session.commit()

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
