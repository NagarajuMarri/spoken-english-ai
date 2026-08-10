"""Enforce one persisted subscription lifecycle per learner."""

from alembic import op

from backend.app.db.schema import ensure_no_duplicate_subscriptions

revision = "0015_subscription_runtime"
down_revision = "0014_native_telugu_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ensure_no_duplicate_subscriptions(op.get_bind())
    with op.batch_alter_table("commercial_subscriptions") as batch_op:
        batch_op.create_unique_constraint(
            "uq_commercial_subscription_learner",
            ["learner_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("commercial_subscriptions") as batch_op:
        batch_op.drop_constraint(
            "uq_commercial_subscription_learner",
            type_="unique",
        )
