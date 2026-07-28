"""Add authentication, refresh tokens, and learner ownership."""

from alembic import op
import sqlalchemy as sa

revision = "0004_auth_ownership"
down_revision = "0003_voice_foundation"
branch_labels = None
depends_on = None


def learners_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "learners",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("native_language", sa.String(20), nullable=False),
        sa.Column("proficiency_level", sa.String(30), nullable=False),
        sa.Column("learning_goal", sa.String(30), nullable=False),
        sa.Column("daily_goal_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email"),
    )


def owned_learners_table(nullable: bool = False) -> sa.Table:
    table = learners_table()
    table.append_column(sa.Column(
        "user_account_id", sa.String(36),
        sa.ForeignKey("user_accounts.id", name="fk_learners_user_account_id", ondelete="CASCADE"),
        nullable=nullable,
    ))
    sa.Index("ix_learners_user_account_id", table.c.user_account_id, unique=True)
    return table


def upgrade() -> None:
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_user_accounts_email"),
    )
    op.create_index("ix_user_accounts_email", "user_accounts", ["email"])
    op.create_index("ix_user_accounts_status", "user_accounts", ["status"])
    op.execute(
        "INSERT INTO user_accounts "
        "(id, email, password_hash, status, email_verified, created_at, updated_at) "
        "SELECT id, email, '!legacy-account-disabled!', 'DISABLED', 0, created_at, updated_at FROM learners"
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_token_id", sa.String(36), sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL")),
        sa.Column("user_agent", sa.String(200), nullable=True),
        sa.Column("ip_metadata", sa.String(80), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])
    with op.batch_alter_table("learners", copy_from=learners_table()) as batch:
        batch.add_column(sa.Column("user_account_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_learners_user_account_id", "user_accounts",
            ["user_account_id"], ["id"], ondelete="CASCADE",
        )
        batch.create_index("ix_learners_user_account_id", ["user_account_id"], unique=True)
    op.execute("UPDATE learners SET user_account_id = id WHERE user_account_id IS NULL")
    with op.batch_alter_table("learners", copy_from=owned_learners_table(nullable=True)) as batch:
        batch.alter_column("user_account_id", existing_type=sa.String(36), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("learners", copy_from=owned_learners_table()) as batch:
        batch.drop_index("ix_learners_user_account_id")
        batch.drop_constraint("fk_learners_user_account_id", type_="foreignkey")
        batch.drop_column("user_account_id")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_user_accounts_status", table_name="user_accounts")
    op.drop_index("ix_user_accounts_email", table_name="user_accounts")
    op.drop_table("user_accounts")
