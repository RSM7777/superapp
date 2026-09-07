"""A mailbox knows which provider it belongs to, and ids are wide enough for
providers other than Gmail.

Microsoft Graph message ids run ~150 characters and its incremental cursor is
a whole URL, against columns sized 32 for Gmail. SQLite ignores VARCHAR
lengths, so the test suite would stay green while Postgres truncated.

Revision ID: 0019
Revises: 0018

Idempotent (create_all races alembic).
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _cols(insp, table):
    return {c["name"]: c for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    sqlite = bind.dialect.name == "sqlite"

    acct = _cols(insp, "gmail_accounts")
    if "provider" not in acct:
        op.add_column("gmail_accounts",
                      sa.Column("provider", sa.String(16), nullable=False,
                                server_default="gmail"))
    if "subscription_id" not in acct:
        op.add_column("gmail_accounts",
                      sa.Column("subscription_id", sa.String(128), nullable=False,
                                server_default=""))

    # Widths. SQLite stores TEXT regardless, so skip the rewrite there.
    if not sqlite:
        op.alter_column("gmail_accounts", "history_id",
                        type_=sa.Text(), existing_type=sa.String(32),
                        existing_nullable=False, server_default=None)
        op.alter_column("inbox_messages", "gmail_msg_id",
                        type_=sa.String(512), existing_type=sa.String(32),
                        existing_nullable=False)
        op.alter_column("inbox_messages", "thread_id",
                        type_=sa.String(256), existing_type=sa.String(32),
                        existing_nullable=True)
        op.alter_column("token_vault", "provider",
                        type_=sa.String(192), existing_type=sa.String(64),
                        existing_nullable=False)

    # One person may hold the same address on two providers.
    names = {c["name"] for c in insp.get_unique_constraints("gmail_accounts")}
    if not sqlite:
        if "uq_gmail_account" in names:
            op.drop_constraint("uq_gmail_account", "gmail_accounts", type_="unique")
        if "uq_mail_account" not in names:
            op.create_unique_constraint("uq_mail_account", "gmail_accounts",
                                        ["user_id", "provider", "email"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if bind.dialect.name == "sqlite":
        return
    names = {c["name"] for c in insp.get_unique_constraints("gmail_accounts")}
    if "uq_mail_account" in names:
        op.drop_constraint("uq_mail_account", "gmail_accounts", type_="unique")
    if "uq_gmail_account" not in names:
        op.create_unique_constraint("uq_gmail_account", "gmail_accounts",
                                    ["user_id", "email"])
    acct = _cols(insp, "gmail_accounts")
    if "subscription_id" in acct:
        op.drop_column("gmail_accounts", "subscription_id")
    if "provider" in acct:
        op.drop_column("gmail_accounts", "provider")
