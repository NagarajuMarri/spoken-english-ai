from __future__ import annotations

import secrets
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.security import hash_password_reset_token
from backend.app.models import PasswordResetToken, SecurityAuditEvent, UserAccount


_AUDIT_REFERENCE_KEY = "password_reset_token_reference"


class PasswordResetJobPermanentError(RuntimeError):
    """A privacy-safe job failure that must not be retried through SMTP."""


class PasswordResetEmailJobHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        delivery,
        *,
        public_frontend_url: str,
    ) -> None:
        self.session_factory = session_factory
        self.delivery = delivery
        self.public_frontend_url = public_frontend_url.rstrip("/")

    def deliver(self, payload: dict[str, str]) -> None:
        reset_id, reset_url = self._payload(payload)
        with self.session_factory() as session:
            reset, user = self._active_reset(session, reset_id, reset_url)
            if self._has_audit(session, reset.id, "PASSWORD_RESET_DELIVERY_SUCCEEDED"):
                return
            recipient = user.email

        self.delivery.deliver(recipient, reset_url)

        with self.session_factory() as session:
            stored_reset = session.get(PasswordResetToken, reset_id)
            if stored_reset is None:
                raise PasswordResetJobPermanentError("Password-reset work is no longer valid.")
            if not self._has_audit(
                session,
                stored_reset.id,
                "PASSWORD_RESET_DELIVERY_SUCCEEDED",
            ):
                session.add(SecurityAuditEvent(
                    event_type="PASSWORD_RESET_DELIVERY_SUCCEEDED",
                    user_id=stored_reset.user_id,
                    outcome="SUCCEEDED",
                    reason_code="smtp_accepted",
                    metadata_json={_AUDIT_REFERENCE_KEY: stored_reset.id},
                ))
                session.commit()

    def terminal_failure(self, payload: dict[str, str]) -> None:
        try:
            reset_id = self._reset_id(payload)
        except PasswordResetJobPermanentError:
            # Malformed allow-listed work has no trustworthy database reference to invalidate.
            return
        with self.session_factory() as session:
            reset = session.get(PasswordResetToken, reset_id)
            if reset is None:
                return
            if reset.used_at is None:
                reset.used_at = datetime.now(timezone.utc)
            if not self._has_audit(session, reset.id, "PASSWORD_RESET_DELIVERY_FAILED"):
                session.add(SecurityAuditEvent(
                    event_type="PASSWORD_RESET_DELIVERY_FAILED",
                    user_id=reset.user_id,
                    outcome="FAILED",
                    reason_code="delivery_retry_limit_reached",
                    metadata_json={_AUDIT_REFERENCE_KEY: reset.id},
                ))
            session.commit()

    def _active_reset(
        self,
        session: Session,
        reset_id: str,
        reset_url: str,
    ) -> tuple[PasswordResetToken, UserAccount]:
        reset = session.get(PasswordResetToken, reset_id)
        if reset is None or reset.used_at is not None:
            raise PasswordResetJobPermanentError("Password-reset work is no longer valid.")
        now = datetime.now(timezone.utc)
        expires_at = reset.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise PasswordResetJobPermanentError("Password-reset work has expired.")
        self._validate_reset_url(reset, reset_url)
        user = session.get(UserAccount, reset.user_id)
        if user is None or user.status != "ACTIVE":
            raise PasswordResetJobPermanentError("Password-reset account is unavailable.")
        return reset, user

    def _validate_reset_url(self, reset: PasswordResetToken, reset_url: str) -> None:
        actual = urlsplit(reset_url)
        expected = urlsplit(self.public_frontend_url)
        expected_path = f"{expected.path.rstrip('/')}/reset-password"
        if (
            actual.scheme != expected.scheme
            or actual.netloc != expected.netloc
            or actual.path != expected_path
            or actual.query
        ):
            raise PasswordResetJobPermanentError("Password-reset destination is invalid.")
        fragment = parse_qs(actual.fragment, keep_blank_values=True)
        raw_values = fragment.get("token", [])
        if len(raw_values) != 1 or len(fragment) != 1:
            raise PasswordResetJobPermanentError("Password-reset token is invalid.")
        candidate_hash = hash_password_reset_token(raw_values[0])
        if not secrets.compare_digest(candidate_hash, reset.token_hash):
            raise PasswordResetJobPermanentError("Password-reset token is invalid.")

    @staticmethod
    def _has_audit(session: Session, reset_id: str, event_type: str) -> bool:
        event_id = session.scalar(
            select(SecurityAuditEvent.id).where(
                SecurityAuditEvent.event_type == event_type,
                SecurityAuditEvent.metadata_json[_AUDIT_REFERENCE_KEY].as_string() == reset_id,
            ).limit(1)
        )
        return event_id is not None

    @classmethod
    def _payload(cls, payload: dict[str, str]) -> tuple[str, str]:
        reset_id = cls._reset_id(payload)
        reset_url = payload.get("reset_url")
        if not isinstance(reset_url, str) or not reset_url:
            raise PasswordResetJobPermanentError("Password-reset destination is missing.")
        return reset_id, reset_url

    @staticmethod
    def _reset_id(payload: dict[str, str]) -> str:
        reset_id = payload.get("password_reset_token_id")
        if not isinstance(reset_id, str) or len(reset_id) != 36:
            raise PasswordResetJobPermanentError("Password-reset reference is invalid.")
        return reset_id
