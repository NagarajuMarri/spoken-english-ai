"""Add durable idempotency and recovery state for AI tutor turns."""

from alembic import op
import sqlalchemy as sa


revision = "0012_ai_turn_reliability"
down_revision = "0011_password_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_turn_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("learner_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("provider_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "conversation_id",
            "idempotency_key",
            name="uq_ai_turn_attempt_identity",
        ),
    )
    op.create_index("ix_ai_turn_attempts_conversation_id", "ai_turn_attempts", ["conversation_id"])
    op.create_index("ix_ai_turn_attempts_learner_id", "ai_turn_attempts", ["learner_id"])
    op.create_index("ix_ai_turn_attempts_status", "ai_turn_attempts", ["status"])
    with op.batch_alter_table("conversation_messages") as batch:
        batch.add_column(sa.Column("ai_turn_attempt_id", sa.String(36)))
        batch.create_foreign_key(
            "fk_conversation_messages_ai_turn_attempt",
            "ai_turn_attempts",
            ["ai_turn_attempt_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_conversation_messages_ai_turn_attempt_id",
        "conversation_messages",
        ["ai_turn_attempt_id"],
        unique=True,
    )
    with op.batch_alter_table("ai_usage_records") as batch:
        batch.add_column(sa.Column("ai_turn_attempt_id", sa.String(36)))
        batch.add_column(
            sa.Column("outcome", sa.String(20), nullable=False, server_default="SUCCESS")
        )
        batch.create_foreign_key(
            "fk_ai_usage_records_ai_turn_attempt",
            "ai_turn_attempts",
            ["ai_turn_attempt_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_ai_usage_records_ai_turn_attempt_id", "ai_usage_records", ["ai_turn_attempt_id"])
    op.create_index(
        "uq_ai_usage_attempt_outcome",
        "ai_usage_records",
        ["ai_turn_attempt_id", "outcome"],
        unique=True,
    )
    with op.batch_alter_table("ai_cost_metric_events") as batch:
        batch.add_column(sa.Column("ai_turn_attempt_id", sa.String(36)))
        batch.create_foreign_key(
            "fk_ai_cost_metric_events_ai_turn_attempt",
            "ai_turn_attempts",
            ["ai_turn_attempt_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_ai_cost_metric_events_ai_turn_attempt_id",
        "ai_cost_metric_events",
        ["ai_turn_attempt_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_cost_metric_events_ai_turn_attempt_id", table_name="ai_cost_metric_events")
    with op.batch_alter_table("ai_cost_metric_events") as batch:
        batch.drop_constraint("fk_ai_cost_metric_events_ai_turn_attempt", type_="foreignkey")
        batch.drop_column("ai_turn_attempt_id")
    op.drop_index("uq_ai_usage_attempt_outcome", table_name="ai_usage_records")
    op.drop_index("ix_ai_usage_records_ai_turn_attempt_id", table_name="ai_usage_records")
    with op.batch_alter_table("ai_usage_records") as batch:
        batch.drop_constraint("fk_ai_usage_records_ai_turn_attempt", type_="foreignkey")
        batch.drop_column("outcome")
        batch.drop_column("ai_turn_attempt_id")
    op.drop_index("ix_conversation_messages_ai_turn_attempt_id", table_name="conversation_messages")
    with op.batch_alter_table("conversation_messages") as batch:
        batch.drop_constraint("fk_conversation_messages_ai_turn_attempt", type_="foreignkey")
        batch.drop_column("ai_turn_attempt_id")
    op.drop_table("ai_turn_attempts")
