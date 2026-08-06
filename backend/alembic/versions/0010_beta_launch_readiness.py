"""Add closed-beta waitlist and customer feedback persistence."""
from alembic import op
import sqlalchemy as sa

revision = "0010_beta_launch_readiness"
down_revision = "0009_commercial_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("beta_waitlist_entries", sa.Column("id", sa.String(36), primary_key=True), sa.Column("email", sa.String(320), nullable=False, unique=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_beta_waitlist_entries_email", "beta_waitlist_entries", ["email"], unique=True)
    op.create_table("beta_feedback", sa.Column("id", sa.String(36), primary_key=True), sa.Column("learner_id", sa.String(36), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False), sa.Column("category", sa.String(30), nullable=False), sa.Column("severity", sa.String(20), nullable=False), sa.Column("message", sa.String(1000), nullable=False), sa.Column("contact_allowed", sa.Boolean(), nullable=False), sa.Column("screenshot_name", sa.String(200)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    for column in ("learner_id", "category", "severity", "created_at"):
        op.create_index(f"ix_beta_feedback_{column}", "beta_feedback", [column])


def downgrade() -> None:
    op.drop_table("beta_feedback")
    op.drop_table("beta_waitlist_entries")
