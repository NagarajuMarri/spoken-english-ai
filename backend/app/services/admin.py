from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AudioAsset, RefreshToken, SecurityAuditEvent, UserAccount
from backend.app.core.security import utc_now


class AdministrativeService:
    """Internal-only boundary. It is intentionally not mounted as an HTTP router."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def set_account_status(self, user_id: str, status: str):
        if status not in {"ACTIVE", "DISABLED", "LOCKED"}:
            raise ValueError("Unsupported administrative account status.")
        account = self.session.get(UserAccount, user_id)
        if account is None:
            raise LookupError("Account not found.")
        account.status = status
        self.session.add(SecurityAuditEvent(
            event_type="ACCOUNT_STATUS_CHANGED",
            user_id=user_id,
            outcome="SUCCEEDED",
            reason_code="internal_administration",
            metadata_json={"status": status},
        ))
        self.session.commit()
        return account

    def disable_account(self, user_id: str):
        return self.set_account_status(user_id, "DISABLED")

    def lock_account(self, user_id: str):
        return self.set_account_status(user_id, "LOCKED")

    def unlock_account(self, user_id: str):
        return self.set_account_status(user_id, "ACTIVE")

    def revoke_all_sessions(self, user_id: str) -> int:
        tokens = list(self.session.scalars(
            select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        ))
        now = utc_now()
        for token in tokens:
            token.revoked_at = now
        self.session.add(SecurityAuditEvent(
            event_type="TOKEN_FAMILY_REVOKED",
            user_id=user_id,
            occurred_at=now,
            outcome="SUCCEEDED",
            reason_code="internal_administration",
            metadata_json={"family_revoked": True},
        ))
        self.session.commit()
        return len(tokens)

    def audit_events(self, user_id: str, start: datetime, end: datetime):
        return list(self.session.scalars(select(SecurityAuditEvent).where(
            SecurityAuditEvent.user_id == user_id,
            SecurityAuditEvent.occurred_at >= start,
            SecurityAuditEvent.occurred_at <= end,
        ).order_by(SecurityAuditEvent.occurred_at)))

    def pending_audio_deletions(self):
        return list(self.session.scalars(
            select(AudioAsset).where(AudioAsset.status == "PENDING_DELETION").order_by(AudioAsset.created_at)
        ))
