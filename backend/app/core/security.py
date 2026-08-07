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
from backend.app.models import Learner, RefreshToken, SecurityAuditEvent, UserAccount


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


def hash_password_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def privacy_minimised_network_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return hashlib.sha256(f"network-throttle:{host}".encode()).hexdigest()


def create_access_token(settings, user_id: str, now: datetime | None = None, session_epoch: int = 0) -> str:
    try:
        keys = settings.signing_keys()
    except (ValueError, TypeError):
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "authentication_unavailable",
            "Authentication signing is not configured.",
        )
    issued = now or utc_now()
    payload = {
        "sub": user_id,
        "type": "access",
        "sev": session_epoch,
        "jti": secrets.token_hex(16),
        "iat": issued,
        "exp": issued + timedelta(minutes=settings.access_token_lifetime_minutes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    active_key = keys[settings.jwt_active_key_id]
    if len(active_key) < 32:
        raise AppError(status.HTTP_503_SERVICE_UNAVAILABLE, "authentication_unavailable", "Authentication signing is not configured.")
    return jwt.encode(
        payload,
        active_key,
        algorithm=settings.jwt_algorithm,
        headers={"kid": settings.jwt_active_key_id},
    )


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
    session: Session
    request_id: str | None
    correlation_id: str | None
    network_key: str
    user_agent: str | None


bearer = HTTPBearer(auto_error=False)


def _audit_access_block(
    session: Session,
    request: Request,
    event_type: str,
    reason: str,
    user: UserAccount | None = None,
) -> None:
    session.add(SecurityAuditEvent(
        event_type=event_type,
        user_id=user.id if user else None,
        outcome="BLOCKED",
        reason_code=reason,
        request_id=getattr(request.state, "request_id", None),
        correlation_id=getattr(request.state, "correlation_id", None),
        privacy_minimised_network_key=privacy_minimised_network_key(request),
        user_agent_summary=(request.headers.get("user-agent") or "")[:100] or None,
        metadata_json={},
    ))
    session.commit()


def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_db),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        _audit_access_block(session, request, "ACCESS_TOKEN_REJECTED", "authentication_required")
        raise AppError(status.HTTP_401_UNAUTHORIZED, "authentication_required", "Authentication required.")
    settings = request.app.state.settings
    try:
        keys = settings.signing_keys()
        header = jwt.get_unverified_header(credentials.credentials)
    except (ValueError, TypeError, jwt.PyJWTError) as exc:
        _audit_access_block(session, request, "ACCESS_TOKEN_REJECTED", "invalid_access_token")
        raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_access_token", "Invalid access token.") from exc
    kid = header.get("kid")
    if kid is None:
        kid = "legacy"
    if kid not in keys or header.get("alg") != settings.jwt_algorithm:
        _audit_access_block(session, request, "ACCESS_TOKEN_REJECTED", "unknown_key_or_algorithm")
        raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_access_token", "Invalid access token.")
    if len(keys[kid]) < 32:
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "authentication_unavailable",
            "Authentication signing is not configured.",
        )
    try:
        claims = jwt.decode(
            credentials.credentials,
            keys[kid],
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "exp", "iat", "iss", "aud", "type", "sev"]},
        )
    except jwt.ExpiredSignatureError as exc:
        _audit_access_block(session, request, "ACCESS_TOKEN_REJECTED", "access_token_expired")
        raise AppError(status.HTTP_401_UNAUTHORIZED, "access_token_expired", "Access token expired.") from exc
    except jwt.PyJWTError as exc:
        _audit_access_block(session, request, "ACCESS_TOKEN_REJECTED", "invalid_access_token")
        raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_access_token", "Invalid access token.") from exc
    if claims.get("type") != "access":
        _audit_access_block(session, request, "ACCESS_TOKEN_REJECTED", "invalid_token_type")
        raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_access_token", "Invalid access token.")
    user = session.get(UserAccount, claims["sub"])
    if user is None or user.status != "ACTIVE":
        _audit_access_block(session, request, "ACCOUNT_STATUS_BLOCKED", "account_unavailable", user)
        raise AppError(status.HTTP_401_UNAUTHORIZED, "account_unavailable", "Account is unavailable.")
    if claims.get("sev") != user.session_epoch:
        _audit_access_block(session, request, "ACCESS_TOKEN_REJECTED", "session_revoked", user)
        raise AppError(status.HTTP_401_UNAUTHORIZED, "session_revoked", "Your session has been revoked.")
    learner = session.scalar(select(Learner).where(Learner.user_account_id == user.id))
    if learner is None:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "account_unavailable", "Account is unavailable.")
    request.state.authenticated_user_id = user.id
    request.state.learner_id = learner.id
    return Principal(
        user,
        learner,
        session,
        getattr(request.state, "request_id", None),
        getattr(request.state, "correlation_id", None),
        privacy_minimised_network_key(request),
        (request.headers.get("user-agent") or "")[:100] or None,
    )


def require_learner_owner(learner_id: str, principal: Principal = Depends(current_principal)) -> Principal:
    ensure_owner(learner_id, principal)
    return principal


def ensure_owner(resource_learner_id: str, principal: Principal) -> None:
    if resource_learner_id != principal.learner.id:
        from backend.app.core.operations import audit_event
        audit_event(
            principal.session,
            "CROSS_USER_ACCESS_BLOCKED",
            principal=principal,
            outcome="BLOCKED",
            reason_code="resource_not_found",
        )
        raise AppError(status.HTTP_404_NOT_FOUND, "resource_not_found", "Resource not found.")
