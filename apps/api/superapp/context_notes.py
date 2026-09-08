"""Save the user's actual words; indexing is retryable and never loses them."""
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from . import memory
from .models import SavedContext


def save_context(db, *, user_id: str, text: str) -> SavedContext:
    body = text.strip()
    if not body:
        raise ValueError("Nothing to remember")
    note_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"nano-context:{user_id}:{body}"))
    note = db.get(SavedContext, note_id)
    if note is None:
        try:
            with db.begin_nested():
                note = SavedContext(id=note_id, user_id=user_id, text=body)
                db.add(note)
                db.flush()
        except IntegrityError:
            note = db.get(SavedContext, note_id)
            if note is None:
                raise
    _index(db, note)
    return note


def _index(db, note) -> None:
    if note.indexed or not memory.available(db):
        return
    try:
        with db.begin_nested():
            count = memory.remember(db, user_id=note.user_id, domain="knowledge", kind="chat",
                ref_id=note.id, content=note.text, title="From our conversation", source="import",
                author="user", source_ref=f"nano:context:{note.id}", event_at=note.created_at)
            note.indexed = bool(count)
    except Exception:
        # The canonical text has already been saved. The dispatcher retries
        # a failed SQL/index write; embedding outages retain pending chunks.
        pass


def recent_context(db, user_id: str) -> list[dict]:
    return [{"text": n.text, "when": n.created_at.isoformat()} for n in db.scalars(
        select(SavedContext).where(SavedContext.user_id == user_id)
        .order_by(SavedContext.created_at.desc(), SavedContext.id).limit(8))]


def index_saved_context(limit: int = 20) -> int:
    from .db import SessionLocal
    with SessionLocal() as db:
        notes = list(db.scalars(select(SavedContext).where(SavedContext.indexed.is_(False))
                               .order_by(SavedContext.created_at).limit(limit)))
        for note in notes:
            _index(db, note)
        db.commit()
        return sum(bool(n.indexed) for n in notes)
