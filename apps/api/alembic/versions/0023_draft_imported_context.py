"""A draft that quotes the user's own imported notes never sends itself.

Recall for a reply is driven by the SENDER'S text, so whoever writes in has a
say in what comes back — and that evidence feeds a reply addressed to them.
Past mail is now scoped to the correspondent, and deliberately imported
material is still used, because using it is the point; but a draft built on
any of it waits for a person, however the rule was delegated.

Revision ID: 0023
Revises: 0022

Idempotent (create_all races alembic).
"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("inbox_drafts")]
    if "used_imported_context" not in cols:
        op.add_column("inbox_drafts",
                      sa.Column("used_imported_context", sa.Boolean, nullable=False,
                                server_default=sa.false()))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("inbox_drafts")]
    if "used_imported_context" in cols:
        op.drop_column("inbox_drafts", "used_imported_context")
