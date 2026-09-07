"""Drafts remember how they were written, not just whether they were sent.

Revision ID: 0019
Revises: 0018

Idempotent (create_all races alembic). Backfills: any draft whose body is the
old failure fallback ("(stub draft)") is marked failed so it can never
auto-send — that fallback invented a cheerful yes whenever the model refused.
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("inbox_drafts")]
    if "generation_status" not in cols:
        op.add_column("inbox_drafts",
                      sa.Column("generation_status", sa.String(16), nullable=False,
                                server_default="ready"))
    if "generation_reason" not in cols:
        op.add_column("inbox_drafts",
                      sa.Column("generation_reason", sa.String(200), nullable=False,
                                server_default=""))
    op.execute(
        "UPDATE inbox_drafts SET generation_status = 'failed', "
        "generation_reason = 'legacy stub draft' "
        "WHERE body LIKE '%(stub draft)%'"
    )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("inbox_drafts")]
    if "generation_reason" in cols:
        op.drop_column("inbox_drafts", "generation_reason")
    if "generation_status" in cols:
        op.drop_column("inbox_drafts", "generation_status")
