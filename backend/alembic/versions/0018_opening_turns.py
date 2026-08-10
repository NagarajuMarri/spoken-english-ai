"""Distinguish persisted system opening utterances from learner turns."""

from alembic import op
import sqlalchemy as sa


revision = "0018_opening_turns"
down_revision = "0017_provider_call_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_turn_attempts") as batch:
        batch.add_column(
            sa.Column(
                "turn_kind",
                sa.String(20),
                nullable=False,
                server_default="LEARNER",
            )
        )
    op.create_index(
        "ix_ai_turn_attempts_turn_kind",
        "ai_turn_attempts",
        ["turn_kind"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_turn_attempts_turn_kind",
        table_name="ai_turn_attempts",
    )
    with op.batch_alter_table("ai_turn_attempts") as batch:
        batch.drop_column("turn_kind")
