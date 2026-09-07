"""Memory keeps provenance, chunks long material, and admits when it failed.
Plus mail_history: the conversation record the inbox twin is not.

Revision ID: 0021
Revises: 0020

Three problems this fixes.

1. `remember()` truncated every entry to 2,000 characters and stored one row
   per source. A decision in the last paragraph of a meeting note was simply
   not in the database. Content is now split into sections, each its own row,
   with chunk_index and a link back to the original.

2. A chunk knew its domain and kind and nothing else: not where it came from,
   who said it, or WHEN IT HAPPENED. Imported history would otherwise look as
   if it all happened on import day, which makes "who matters to me" noise.
   `event_at` is the original date; `created_at` stays the insert time.

3. On an embedding failure the code stored a hash-projection vector that looks
   like a real embedding and retrieves nothing meaningful. Rows now carry
   `embed_status`, keep their text, and are retried — a degraded search says so.

mail_history holds sent and archived conversation that the inbox twin
deliberately excludes: `SENT` is in SKIP_LABELS, so "have I replied to this
sender before" had no data to read. It is a record for context and signals, not
a queue — nothing in it is ever triaged, drafted for, archived or replied to.
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "mail_history" not in insp.get_table_names():
        op.create_table(
            "mail_history",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(64), nullable=False),
            sa.Column("account_email", sa.String(128), nullable=False, server_default=""),
            sa.Column("gmail_msg_id", sa.String(32), nullable=False),
            sa.Column("thread_id", sa.String(32), nullable=False, server_default=""),
            # 'inbound' (they wrote) | 'outbound' (the user wrote). Outbound is
            # the negative filter that makes "unanswered" and "I reply to this
            # person" honest.
            sa.Column("direction", sa.String(8), nullable=False, server_default="inbound"),
            sa.Column("from_addr", sa.String(320), nullable=False, server_default=""),
            sa.Column("to_addrs", sa.Text(), nullable=False, server_default=""),
            sa.Column("subject", sa.String(256), nullable=False, server_default=""),
            sa.Column("body_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "gmail_msg_id", name="uq_mail_history_msg"),
        )
        op.create_index("ix_mail_history_sender", "mail_history",
                        ["user_id", "from_addr"])
        op.create_index("ix_mail_history_thread", "mail_history",
                        ["user_id", "thread_id"])

    if bind.dialect.name != "postgresql":
        return  # memory_chunks is Postgres-only; SQLite dev simply recalls nothing
    if "memory_chunks" not in insp.get_table_names():
        return  # 0009 skipped (no pgvector); nothing to upgrade

    cols = [c["name"] for c in insp.get_columns("memory_chunks")]
    add = []
    if "source" not in cols:
        add.append("ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT ''")
    if "author" not in cols:
        add.append("ADD COLUMN author VARCHAR(320) NOT NULL DEFAULT ''")
    if "title" not in cols:
        add.append("ADD COLUMN title VARCHAR(256) NOT NULL DEFAULT ''")
    if "source_ref" not in cols:
        add.append("ADD COLUMN source_ref VARCHAR(512) NOT NULL DEFAULT ''")
    if "project" not in cols:
        add.append("ADD COLUMN project VARCHAR(120) NOT NULL DEFAULT ''")
    if "chunk_index" not in cols:
        add.append("ADD COLUMN chunk_index INTEGER NOT NULL DEFAULT 0")
    if "event_at" not in cols:
        add.append("ADD COLUMN event_at TIMESTAMPTZ")
    if "embed_status" not in cols:
        add.append("ADD COLUMN embed_status VARCHAR(12) NOT NULL DEFAULT 'ok'")
    if add:
        op.execute("ALTER TABLE memory_chunks " + ", ".join(add))

    # One row per (user, kind, ref) becomes one row per chunk of it.
    op.execute("ALTER TABLE memory_chunks DROP CONSTRAINT IF EXISTS memory_chunks_user_id_kind_ref_id_key")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_chunk
                  ON memory_chunks (user_id, kind, ref_id, chunk_index)""")
    # Existing rows were written before provenance; event time is all we can
    # infer, and the insert time is the honest best guess for it.
    op.execute("UPDATE memory_chunks SET event_at = created_at WHERE event_at IS NULL")
    # Retrieval was an exact scan over every row. At a few thousand rows that is
    # fine; a "vast DB of knowledge" is exactly what it is not. hnsw needs
    # pgvector >= 0.5 — an older extension must degrade to a slower search, not
    # take the whole migration down with it.
    op.execute("""
        DO $$
        BEGIN
            CREATE INDEX IF NOT EXISTS ix_memory_embedding
              ON memory_chunks USING hnsw (embedding vector_cosine_ops);
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'hnsw index unavailable (%); recall stays exact-scan', SQLERRM;
        END $$;
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS ix_memory_retry
                  ON memory_chunks (user_id) WHERE embed_status <> 'ok'""")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "mail_history" in insp.get_table_names():
        op.drop_table("mail_history")
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_memory_embedding")
    op.execute("DROP INDEX IF EXISTS ix_memory_retry")
    op.execute("DROP INDEX IF EXISTS uq_memory_chunk")
    for col in ("source", "author", "title", "source_ref", "project",
                "chunk_index", "event_at", "embed_status"):
        op.execute(f"ALTER TABLE memory_chunks DROP COLUMN IF EXISTS {col}")
