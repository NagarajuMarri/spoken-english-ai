"""Add lesson sessions, evaluations, and progress dimensions."""

from alembic import op
import sqlalchemy as sa

revision = "0002_curriculum_progress"
down_revision = "0001_learner_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("progress_records") as batch:
        batch.add_column(sa.Column("lesson_id", sa.String(80), nullable=True))
        batch.add_column(sa.Column("practice_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("scenario_id", sa.String(50), nullable=True))
        batch.add_column(sa.Column("proficiency_level", sa.String(30), nullable=True))
    op.create_table(
        "lesson_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lesson_id", sa.String(80), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
    )
    op.create_index("ix_lesson_sessions_learner_id", "lesson_sessions", ["learner_id"])
    op.create_index("ix_lesson_sessions_lesson_id", "lesson_sessions", ["lesson_id"])
    op.create_table(
        "conversation_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lesson_session_id", sa.String(36), sa.ForeignKey("lesson_sessions.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("grammar_score", sa.Integer(), nullable=False),
        sa.Column("vocabulary_score", sa.Integer(), nullable=False),
        sa.Column("fluency_score", sa.Integer(), nullable=False),
        sa.Column("task_completion_score", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("priority_improvements", sa.JSON(), nullable=False),
        sa.Column("corrected_examples", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("conversation_evaluations")
    op.drop_index("ix_lesson_sessions_lesson_id", table_name="lesson_sessions")
    op.drop_index("ix_lesson_sessions_learner_id", table_name="lesson_sessions")
    op.drop_table("lesson_sessions")
    with op.batch_alter_table("progress_records") as batch:
        for column in ("proficiency_level", "scenario_id", "score", "duration_seconds", "practice_date", "lesson_id"):
            batch.drop_column(column)
