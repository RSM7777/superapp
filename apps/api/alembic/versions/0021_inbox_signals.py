"""Headers kept at ingest, deterministic signals, and importance separated
from reply-obligation.

Revision ID: 0021
Revises: 0020

Two changes, both prerequisites for scoring triage against a labelled corpus.

1. The Gmail parser kept only From and Subject, so "addressed to me or to four
   hundred people", "is this a reply in a thread I started" and "is this bulk
   mail" were unanswerable — the very signals that separate one person's
   important mail from another's. The headers are now stored.

2. "Which of four piles" conflated two questions. A dishwasher recall is
   important and needs no reply; a scheduling ping needs a reply and is not
   important. Labels written against the single tier would have to be rewritten
   when the split lands, so the fields land first. `tier` stays authoritative
   for display and behaviour until a golden set exists to prove a change safe.

Idempotent (create_all races alembic).
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_TEXT_COLS = [
    ("to_addrs", sa.Text(), ""),
    ("cc_addrs", sa.Text(), ""),
    ("reply_to", sa.String(320), ""),
    ("message_id_hdr", sa.String(320), ""),
    ("in_reply_to", sa.String(320), ""),
    ("list_id", sa.String(320), ""),
    ("precedence", sa.String(32), ""),
    ("importance", sa.String(8), "normal"),
]


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("inbox_messages")]
    for name, type_, default in _TEXT_COLS:
        if name not in cols:
            op.add_column("inbox_messages",
                          sa.Column(name, type_, nullable=False, server_default=default))
    if "has_list_unsubscribe" not in cols:
        op.add_column("inbox_messages", sa.Column(
            "has_list_unsubscribe", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "requires_reply" not in cols:
        op.add_column("inbox_messages", sa.Column(
            "requires_reply", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "attention_deadline" not in cols:
        op.add_column("inbox_messages", sa.Column(
            "attention_deadline", sa.DateTime(timezone=True), nullable=True))
    if "signals" not in cols:
        op.add_column("inbox_messages", sa.Column("signals", sa.JSON(), nullable=True))
    # Backfill the reply obligation for rows triaged before the split, so a
    # corpus labelled today can include history: needs_reply meant exactly this.
    op.execute("UPDATE inbox_messages SET requires_reply = true WHERE tier = 'needs_reply'")


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("inbox_messages")]
    for name in ("signals", "attention_deadline", "requires_reply", "has_list_unsubscribe",
                 *[c[0] for c in _TEXT_COLS]):
        if name in cols:
            op.drop_column("inbox_messages", name)
