"""Add provider-neutral AI memory, usage, and voice processing state."""

from alembic import op
import sqlalchemy as sa

revision = "0006_ai_conversation_voice"
down_revision = "0005_operations_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learner_memory_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("current_level", sa.String(30), nullable=False),
        sa.Column("preferred_topics", sa.JSON(), nullable=False),
        sa.Column("avoided_topics", sa.JSON(), nullable=False),
        sa.Column("recent_goals", sa.JSON(), nullable=False),
        sa.Column("completed_goals", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("learner_id"),
    )
    op.create_index("ix_memory_profile_learner", "learner_memory_profiles", ["learner_id"])
    op.create_table(
        "learner_memory_signals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("normalised_value", sa.String(200), nullable=False),
        sa.Column("display_value", sa.String(200), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("trend_value", sa.Float(), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("learner_id", "category", "normalised_value", name="uq_memory_signal"),
    )
    op.create_index("ix_memory_signal_learner_category", "learner_memory_signals", ["learner_id", "category"])
    op.create_table(
        "ai_usage_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("voice_session_id", sa.String(36), nullable=True),
        sa.Column("provider_kind", sa.String(20), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("input_units", sa.Float(), nullable=False),
        sa.Column("output_units", sa.Float(), nullable=False),
        sa.Column("retries", sa.Integer(), nullable=False),
        sa.Column("degraded", sa.Boolean(), nullable=False),
        sa.Column("failed", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_usage_learner_time", "ai_usage_records", ["learner_id", "occurred_at"])
    op.create_index("ix_ai_usage_user_time", "ai_usage_records", ["user_id", "occurred_at"])
    op.create_index("ix_ai_usage_session", "ai_usage_records", ["voice_session_id"])
    op.create_table(
        "voice_processing_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("voice_turn_id", sa.String(36), sa.ForeignKey("voice_turns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("degraded_features", sa.JSON(), nullable=False),
        sa.Column("failure_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("voice_turn_id", "idempotency_key", name="uq_voice_processing_identity"),
    )
    op.create_index("ix_voice_processing_learner_status", "voice_processing_attempts", ["learner_id", "status"])
    op.create_index("ix_voice_processing_turn", "voice_processing_attempts", ["voice_turn_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_processing_turn", table_name="voice_processing_attempts")
    op.drop_index("ix_voice_processing_learner_status", table_name="voice_processing_attempts")
    op.drop_table("voice_processing_attempts")
    op.drop_index("ix_ai_usage_session", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_user_time", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_learner_time", table_name="ai_usage_records")
    op.drop_table("ai_usage_records")
    op.drop_index("ix_memory_signal_learner_category", table_name="learner_memory_signals")
    op.drop_table("learner_memory_signals")
    op.drop_index("ix_memory_profile_learner", table_name="learner_memory_profiles")
    op.drop_table("learner_memory_profiles")
