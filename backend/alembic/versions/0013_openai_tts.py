"""Add durable OpenAI TTS generation state and cached audio bytes."""

from alembic import op
import sqlalchemy as sa


revision = "0013_openai_tts"
down_revision = "0012_ai_turn_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tts_synthesis_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ai_turn_attempt_id", sa.String(36), sa.ForeignKey("ai_turn_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tutor_id", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model_used", sa.String(100), nullable=False),
        sa.Column("voice_used", sa.String(50), nullable=False),
        sa.Column("spoken_text_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("failure_code", sa.String(80), nullable=True),
        sa.Column("content_type", sa.String(50), nullable=True),
        sa.Column("audio_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("audio_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_characters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation_latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("usage_classification", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("ai_turn_attempt_id"),
    )
    op.create_index("ix_tts_synthesis_attempts_ai_turn_attempt_id", "tts_synthesis_attempts", ["ai_turn_attempt_id"], unique=True)
    op.create_index("ix_tts_synthesis_attempts_learner_id", "tts_synthesis_attempts", ["learner_id"])
    op.create_index("ix_tts_synthesis_attempts_status", "tts_synthesis_attempts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tts_synthesis_attempts_status", table_name="tts_synthesis_attempts")
    op.drop_index("ix_tts_synthesis_attempts_learner_id", table_name="tts_synthesis_attempts")
    op.drop_index("ix_tts_synthesis_attempts_ai_turn_attempt_id", table_name="tts_synthesis_attempts")
    op.drop_table("tts_synthesis_attempts")
