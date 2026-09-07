"""The auto-reply grace window: a deadline on inbox_drafts.

Revision ID: 0018
Revises: 0017

Idempotent (create_all races alembic).
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("inbox_drafts")]
    if "auto_send_at" not in cols:
        op.add_column("inbox_drafts",
                      sa.Column("auto_send_at", sa.DateTime(timezone=True), nullable=True))
    if "edited_at" not in cols:
        op.add_column("inbox_drafts",
                      sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
    if "claimed_at" not in cols:
        op.add_column("inbox_drafts",
                      sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("inbox_drafts")]
    if "auto_send_at" in cols:
        op.drop_column("inbox_drafts", "auto_send_at")
    if "edited_at" in cols:
        op.drop_column("inbox_drafts", "edited_at")
    if "claimed_at" in cols:
        op.drop_column("inbox_drafts", "claimed_at")
