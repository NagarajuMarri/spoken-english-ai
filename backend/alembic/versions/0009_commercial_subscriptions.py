"""Add commercial subscriptions, payment events, and refund records."""

from alembic import op
import sqlalchemy as sa

revision = "0009_commercial_subscriptions"
down_revision = "0008_intelligent_learning_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("commercial_subscriptions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False), sa.Column("plan_id", sa.String(40), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("provider_id", sa.String(40)), sa.Column("provider_reference", sa.String(160), unique=True), sa.Column("trial_started_at", sa.DateTime(timezone=True)), sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    for column in ("learner_id", "plan_id", "status", "current_period_end"):
        op.create_index(f"ix_commercial_subscriptions_{column}", "commercial_subscriptions", [column])
    op.create_table("commercial_payment_events", sa.Column("event_id", sa.String(100), primary_key=True), sa.Column("subscription_id", sa.String(36), sa.ForeignKey("commercial_subscriptions.id", ondelete="CASCADE"), nullable=False), sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False), sa.Column("event_type", sa.String(50), nullable=False), sa.Column("provider_id", sa.String(40), nullable=False), sa.Column("provider_reference", sa.String(160), nullable=False), sa.Column("payload_digest", sa.String(64), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    for column in ("subscription_id", "learner_id", "event_type", "occurred_at"):
        op.create_index(f"ix_commercial_payment_events_{column}", "commercial_payment_events", [column])
    op.create_table("commercial_refund_records", sa.Column("id", sa.String(36), primary_key=True), sa.Column("subscription_id", sa.String(36), sa.ForeignKey("commercial_subscriptions.id", ondelete="CASCADE"), nullable=False), sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False), sa.Column("reason", sa.String(300), nullable=False), sa.Column("requested_by", sa.String(100), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_commercial_refund_records_subscription_id", "commercial_refund_records", ["subscription_id"])
    op.create_index("ix_commercial_refund_records_learner_id", "commercial_refund_records", ["learner_id"])
    op.create_table("commercial_audit_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("subscription_id", sa.String(36), sa.ForeignKey("commercial_subscriptions.id", ondelete="SET NULL")), sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="SET NULL")), sa.Column("action", sa.String(60), nullable=False), sa.Column("outcome", sa.String(20), nullable=False), sa.Column("metadata_json", sa.JSON(), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    for column in ("subscription_id", "learner_id", "action", "occurred_at"):
        op.create_index(f"ix_commercial_audit_events_{column}", "commercial_audit_events", [column])


def downgrade() -> None:
    op.drop_table("commercial_audit_events")
    op.drop_table("commercial_refund_records")
    op.drop_table("commercial_payment_events")
    op.drop_table("commercial_subscriptions")
