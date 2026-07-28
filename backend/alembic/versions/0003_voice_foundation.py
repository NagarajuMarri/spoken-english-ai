"""Add consent-aware voice practice metadata."""

from alembic import op
import sqlalchemy as sa

revision = "0003_voice_foundation"
down_revision = "0002_curriculum_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("voice_processing_consent", sa.Boolean(), nullable=False),
        sa.Column("audio_storage_consent", sa.Boolean(), nullable=False),
        sa.Column("consent_version", sa.String(30), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_consent_records_learner_id", "consent_records", ["learner_id"])
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_id", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voice_sessions_learner_id", "voice_sessions", ["learner_id"])
    op.create_table(
        "audio_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("voice_session_id", sa.String(36), sa.ForeignKey("voice_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_type", sa.String(50), nullable=False),
        sa.Column("storage_key", sa.String(200), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audio_assets_learner_id", "audio_assets", ["learner_id"])
    op.create_index("ix_audio_assets_voice_session_id", "audio_assets", ["voice_session_id"])
    op.create_table(
        "voice_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("voice_session_id", sa.String(36), sa.ForeignKey("voice_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("audio_asset_id", sa.String(36), sa.ForeignKey("audio_assets.id"), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("tutor_text", sa.Text(), nullable=False),
        sa.Column("correction_summary", sa.Text(), nullable=True),
        sa.Column("synthetic_audio_reference", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("voice_session_id", "turn_number"),
    )
    op.create_index("ix_voice_turns_voice_session_id", "voice_turns", ["voice_session_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_turns_voice_session_id", table_name="voice_turns")
    op.drop_table("voice_turns")
    op.drop_index("ix_audio_assets_voice_session_id", table_name="audio_assets")
    op.drop_index("ix_audio_assets_learner_id", table_name="audio_assets")
    op.drop_table("audio_assets")
    op.drop_index("ix_voice_sessions_learner_id", table_name="voice_sessions")
    op.drop_table("voice_sessions")
    op.drop_index("ix_consent_records_learner_id", table_name="consent_records")
    op.drop_table("consent_records")
