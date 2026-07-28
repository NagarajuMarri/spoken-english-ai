from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Protocol

import bcrypt
import jwt
from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.db.session import get_db
from backend.app.models import Learner, RefreshToken, UserAccount


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def privacy_minimised_network_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return hashlib.sha256(f"network-throttle:{host}".encode()).hexdigest()


def create_access_token(settings, user_id: str, now: datetime | None = None) -> str:
    if len(settings.jwt_secret) < 32:
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "authentication_unavailable",
            "Authentication signing is not configured.",
        )
    issued = now or utc_now()
    payload = {
        "sub": user_id,
        "type": "access",
        "jti": secrets.token_hex(16),
        "iat": issued,
        "exp": issued + timedelta(minutes=settings.access_token_lifetime_minutes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class LoginThrottler(Protocol):
    def check(self, key: str) -> None: ...
    def failed(self, key: str) -> None: ...
    def succeeded(self, key: str) -> None: ...


class InMemoryLoginThrottler:
    def __init__(self, limit: int = 5) -> None:
        self.limit = limit
        self.attempts: dict[str, int] = {}

    def check(self, key: str) -> None:
        if self.attempts.get(key, 0) >= self.limit:
            raise AppError(status.HTTP_429_TOO_MANY_REQUESTS, "login_throttled", "Too many login attempts.")

    def failed(self, key: str) -> None:
        self.attempts[key] = self.attempts.get(key, 0) + 1

    def succeeded(self, key: str) -> None:
        self.attempts.pop(key, None)


@dataclass(frozen=True)
class Principal:
    user: UserAccount
    learner: Learner


bearer = HTTPBearer(auto_error=False)


def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_db),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(status.HTTP_401_UNAUTHORIZED, "authentication_required", "Authentication required.")
    settings = request.app.state.settings
    if len(settings.jwt_secret) < 32:
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "authentication_unavailable",
            "Authentication signing is not configured.",
        )
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "exp", "iat", "iss", "aud", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "access_token_expired", "Access token expired.") from exc
    except jwt.PyJWTError as exc:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_access_token", "Invalid access token.") from exc
    if claims.get("type") != "access":
        raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_access_token", "Invalid access token.")
    user = session.get(UserAccount, claims["sub"])
    if user is None or user.status != "ACTIVE":
        raise AppError(status.HTTP_401_UNAUTHORIZED, "account_unavailable", "Account is unavailable.")
    learner = session.scalar(select(Learner).where(Learner.user_account_id == user.id))
    if learner is None:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "account_unavailable", "Account is unavailable.")
    return Principal(user, learner)


def require_learner_owner(learner_id: str, principal: Principal = Depends(current_principal)) -> Principal:
    if learner_id != principal.learner.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "resource_not_found", "Resource not found.")
    return principal


def ensure_owner(resource_learner_id: str, principal: Principal) -> None:
    if resource_learner_id != principal.learner.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "resource_not_found", "Resource not found.")
