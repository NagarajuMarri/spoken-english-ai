"""Add cost-aware intelligent learning persistence."""

from alembic import op
import sqlalchemy as sa

revision = "0008_intelligent_learning_engine"
down_revision = "0007_avatar_tutor_experience"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("lesson_cache_entries", sa.Column("id", sa.String(36), primary_key=True), sa.Column("cache_key", sa.String(160), nullable=False), sa.Column("content_kind", sa.String(40), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("invalidated_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("cache_key", "content_kind", "version"))
    op.create_index("ix_lesson_cache_entries_cache_key", "lesson_cache_entries", ["cache_key"])
    op.create_index("ix_lesson_cache_entries_content_kind", "lesson_cache_entries", ["content_kind"])
    op.create_index("ix_lesson_cache_entries_expires_at", "lesson_cache_entries", ["expires_at"])
    op.create_table("tts_audio_cache_entries", sa.Column("cache_key", sa.String(64), primary_key=True), sa.Column("tutor_voice", sa.String(100), nullable=False), sa.Column("privacy_scope", sa.String(100), nullable=False), sa.Column("audio_reference", sa.String(200), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_tts_audio_cache_entries_tutor_voice", "tts_audio_cache_entries", ["tutor_voice"])
    op.create_index("ix_tts_audio_cache_entries_privacy_scope", "tts_audio_cache_entries", ["privacy_scope"])
    op.create_index("ix_tts_audio_cache_entries_expires_at", "tts_audio_cache_entries", ["expires_at"])
    op.create_table("conversation_summary_records", sa.Column("id", sa.String(36), primary_key=True), sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), unique=True, nullable=False), sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False), sa.Column("summary_version", sa.Integer(), nullable=False), sa.Column("pedagogical_signals", sa.JSON(), nullable=False), sa.Column("summarized_through_turn", sa.Integer(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_conversation_summary_records_learner_id", "conversation_summary_records", ["learner_id"])
    op.create_table("ai_cost_metric_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False), sa.Column("lesson_id", sa.String(80), nullable=False), sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False), sa.Column("prompt_tokens", sa.Integer(), nullable=False), sa.Column("completion_tokens", sa.Integer(), nullable=False), sa.Column("cached_tokens", sa.Integer(), nullable=False), sa.Column("estimated_cost_usd", sa.Float(), nullable=False), sa.Column("response_latency_ms", sa.Float(), nullable=False), sa.Column("cache_hit", sa.Boolean(), nullable=False), sa.Column("model_used", sa.String(100), nullable=False), sa.Column("cost_classification", sa.String(40), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    for column in ("learner_id", "lesson_id", "conversation_id", "occurred_at"):
        op.create_index(f"ix_ai_cost_metric_events_{column}", "ai_cost_metric_events", [column])


def downgrade() -> None:
    op.drop_table("ai_cost_metric_events")
    op.drop_table("conversation_summary_records")
    op.drop_table("tts_audio_cache_entries")
    op.drop_table("lesson_cache_entries")
