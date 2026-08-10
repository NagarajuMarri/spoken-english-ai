"""Add dated provider-call reservations for quota attribution."""

from alembic import op
import sqlalchemy as sa

revision = "0017_provider_call_events"
down_revision = "0016_stt_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_call_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation_kind", sa.String(30), nullable=False),
        sa.Column("attempt_reference", sa.String(100), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_units", sa.Float(), nullable=False),
        sa.Column("output_units", sa.Float(), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("failed", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    for column in (
        "learner_id",
        "user_id",
        "operation_kind",
        "attempt_reference",
        "outcome",
        "occurred_at",
    ):
        op.create_index(
            f"ix_provider_call_events_{column}",
            "provider_call_events",
            [column],
        )


def downgrade() -> None:
    op.drop_table("provider_call_events")
