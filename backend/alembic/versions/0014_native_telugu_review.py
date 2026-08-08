"""Add explicit learner language mode for native Telugu review."""

from alembic import op
import sqlalchemy as sa


revision = "0014_native_telugu_review"
down_revision = "0013_openai_tts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("learners") as batch:
        batch.add_column(
            sa.Column("language_mode", sa.String(30), nullable=False, server_default="ENGLISH")
        )
    op.execute(
        "UPDATE learners SET language_mode = 'ENGLISH_TELUGU' "
        "WHERE telugu_explanations_enabled = 1"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE learners SET telugu_explanations_enabled = CASE "
        "WHEN language_mode = 'ENGLISH' THEN 0 ELSE 1 END"
    )
    with op.batch_alter_table("learners") as batch:
        batch.drop_column("language_mode")
