"""Persist 'never miss' promotions on inbox_messages so every auto-send path
can refuse to answer mail the model saw no ask in.

Revision ID: 0017
Revises: 0016

Idempotent (create_all races alembic).
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("inbox_messages")]
    if "rule_promoted" not in cols:
        op.add_column("inbox_messages",
                      sa.Column("rule_promoted", sa.Boolean, nullable=False,
                                server_default=sa.false()))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("inbox_messages")]
    if "rule_promoted" in cols:
        op.drop_column("inbox_messages", "rule_promoted")
