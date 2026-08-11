"""Add canonical mobile identity and reset-code attempt state."""

from alembic import op
import sqlalchemy as sa

revision = "0020_auth_mobile_reset_codes"
down_revision = "0019_realtime_turns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_accounts") as batch:
        batch.add_column(sa.Column("mobile_number", sa.String(16), nullable=True))
        batch.create_unique_constraint("uq_user_accounts_mobile_number", ["mobile_number"])
        batch.create_index("ix_user_accounts_mobile_number", ["mobile_number"])
    with op.batch_alter_table("password_reset_tokens") as batch:
        batch.add_column(sa.Column("verification_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("password_reset_tokens") as batch:
        batch.drop_column("verification_attempts")
    with op.batch_alter_table("user_accounts") as batch:
        batch.drop_index("ix_user_accounts_mobile_number")
        batch.drop_constraint("uq_user_accounts_mobile_number", type_="unique")
        batch.drop_column("mobile_number")
