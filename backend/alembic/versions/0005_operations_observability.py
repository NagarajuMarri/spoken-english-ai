"""Add operational indexes and audio cleanup metadata."""

from alembic import op
import sqlalchemy as sa

revision = "0005_operations_observability"
down_revision = "0004_auth_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audio_assets", sa.Column("cleanup_retry_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("audio_assets", sa.Column("cleanup_failure_reason", sa.String(200), nullable=True))
    op.add_column("audio_assets", sa.Column("deletion_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_audio_assets_cleanup_scan", "audio_assets", ["status", "expires_at", "created_at"])
    op.create_index("ix_refresh_tokens_family_active", "refresh_tokens", ["family_id", "revoked_at"])
    op.create_index("ix_refresh_tokens_expiry_active", "refresh_tokens", ["expires_at", "revoked_at"])
    op.create_index("ix_security_audit_user_time", "security_audit_events", ["user_id", "occurred_at"])
    op.create_index("ix_security_audit_type_time", "security_audit_events", ["event_type", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_security_audit_type_time", table_name="security_audit_events")
    op.drop_index("ix_security_audit_user_time", table_name="security_audit_events")
    op.drop_index("ix_refresh_tokens_expiry_active", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_active", table_name="refresh_tokens")
    op.drop_index("ix_audio_assets_cleanup_scan", table_name="audio_assets")
    op.drop_column("audio_assets", "deletion_confirmed_at")
    op.drop_column("audio_assets", "cleanup_failure_reason")
    op.drop_column("audio_assets", "cleanup_retry_count")
