"""Add learner tutor preferences for the Milestone 8 experience."""

from alembic import op
import sqlalchemy as sa

revision = "0007_avatar_tutor_experience"
down_revision = "0006_ai_conversation_voice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learners",
        sa.Column("preferred_tutor_id", sa.String(50), nullable=False, server_default="ananya"),
    )
    op.add_column(
        "learners",
        sa.Column(
            "telugu_explanations_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("learners", "telugu_explanations_enabled")
    op.drop_column("learners", "preferred_tutor_id")
