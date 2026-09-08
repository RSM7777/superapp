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
    # The offline mailbox predates `provider` and would be backfilled to
    # "gmail" like everything else. It holds a placeholder credential, so the
    # real Gmail client would raise on it and every sync would fail with no
    # way back. Unguarded, so it also repairs a database where create_all
    # added the column before this migration ran.
    op.execute("UPDATE gmail_accounts SET provider='stub' "
               "WHERE email='stub@example.com'")
    if "subscription_id" not in acct:
        op.add_column("gmail_accounts",
                      sa.Column("subscription_id", sa.String(128), nullable=False,
                                server_default=""))

    # Widths. SQLite stores TEXT regardless, so skip the rewrite there.
    if not sqlite:
        # Widen only. Passing server_default would DROP whatever default the
        # column has, leaving NOT NULL with nothing to fall back on and
        # breaking any insert that omits the cursor.
        op.alter_column("gmail_accounts", "history_id",
                        type_=sa.Text(), existing_type=sa.String(32),
                        existing_nullable=False)
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
