"""Create learner onboarding and conversation tables."""

from alembic import op
import sqlalchemy as sa

revision = "0001_learner_onboarding"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learners",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("native_language", sa.String(20), nullable=False),
        sa.Column("proficiency_level", sa.String(30), nullable=False),
        sa.Column("learning_goal", sa.String(30), nullable=False),
        sa.Column("daily_goal_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_learners_email", "learners", ["email"])
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_id", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversations_learner_id", "conversations", ["learner_id"])
    op.create_index("ix_conversations_scenario_id", "conversations", ["scenario_id"])
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("learner_text", sa.Text(), nullable=False),
        sa.Column("tutor_response", sa.Text(), nullable=False),
        sa.Column("correction_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_id", "turn_number"),
    )
    op.create_index("ix_conversation_messages_conversation_id", "conversation_messages", ["conversation_id"])
    op.create_table(
        "progress_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_turns", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_progress_records_learner_id", "progress_records", ["learner_id"])


def downgrade() -> None:
    op.drop_table("progress_records")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
    op.drop_table("learners")
