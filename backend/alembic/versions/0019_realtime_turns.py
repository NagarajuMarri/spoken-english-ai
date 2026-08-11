"""Persist idempotent Realtime learner and tutor turns."""

from alembic import op
import sqlalchemy as sa

revision = "0019_realtime_turns"
down_revision = "0018_opening_turns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "realtime_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("learner_item_id", sa.String(100), nullable=False),
        sa.Column("tutor_response_id", sa.String(100), nullable=True),
        sa.Column("learner_transcript", sa.Text(), nullable=False),
        sa.Column("tutor_transcript", sa.Text(), nullable=True),
        sa.Column("tutor_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("correction_summary", sa.Text(), nullable=True),
        sa.Column("analysis_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("conversation_message_id", sa.String(36), sa.ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_id", "learner_item_id", name="uq_realtime_learner_item"),
        sa.UniqueConstraint("conversation_id", "tutor_response_id", name="uq_realtime_tutor_response"),
    )
    op.create_index("ix_realtime_turns_conversation_id", "realtime_turns", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_realtime_turns_conversation_id", table_name="realtime_turns")
    op.drop_table("realtime_turns")
