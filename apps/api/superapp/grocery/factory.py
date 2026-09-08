"""The one place that turns a link row into a working store client."""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GroceryLink
from ..vault import get_token
from .base import StoreClient, StoreNotConnected
from .providers import InstacartStore, ListStore, WalmartStore

_CLASSES = {"walmart": WalmartStore, "instacart": InstacartStore}


def links(db: Session, user_id: str) -> list[GroceryLink]:
    return list(db.scalars(select(GroceryLink).where(GroceryLink.user_id == user_id)
                           .order_by(GroceryLink.created_at)))


def client_for(db: Session, user_id: str, platform: str) -> StoreClient:
    """A client for one platform, or a raise. Never a silent fallback to the
    list — "I added it to your list" when the person asked to order is a
    different outcome, and they have to be told which one happened."""
    platform = (platform or "list").strip().lower()
    if platform == "list":
        return ListStore()
    cls = _CLASSES.get(platform)
    if cls is None:
        raise StoreNotConnected(f"Nano doesn't know a store called {platform!r}.")
    row = db.scalar(select(GroceryLink).where(
        GroceryLink.user_id == user_id, GroceryLink.platform == platform,
        GroceryLink.status == "linked"))
    if row is None:
        raise StoreNotConnected(f"{platform.title()} isn't linked. Link it in settings first.")
    raw = get_token(db, user_id=user_id, provider=f"grocery:{platform}")
    return cls(json.loads(raw) if raw else {"linked": True})
