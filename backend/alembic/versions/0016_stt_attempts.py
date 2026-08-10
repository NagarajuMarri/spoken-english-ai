"""Add idempotent, privacy-minimised STT quota attempts."""

from alembic import op
import sqlalchemy as sa

revision = "0016_stt_attempts"
down_revision = "0015_subscription_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_transcription_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("audio_digest", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("charge_duration_ms", sa.Integer(), nullable=False),
        sa.Column("provider_requests", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "conversation_id",
            "idempotency_key",
            name="uq_voice_transcription_identity",
        ),
    )
    for column in ("conversation_id", "learner_id", "status", "created_at"):
        op.create_index(
            f"ix_voice_transcription_attempts_{column}",
            "voice_transcription_attempts",
            [column],
        )


def downgrade() -> None:
    op.drop_table("voice_transcription_attempts")
