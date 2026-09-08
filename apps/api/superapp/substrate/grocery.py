"""Grocery twin operations — the only module touching the grocery tables.

The shelf in the design is this file's `grocery_context`: items grouped by
category, plus the two shelves the forecast produces (Running low, Out of
stock). Everything here is deterministic; the model's only job in this vertical
is reading receipts, which happens in the agent.
"""
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..grocery.predict import CATEGORY_DAYS, forecast
from ..models import (GroceryItem, GroceryLink, GroceryOrder, GroceryPurchase,
                      utcnow)

# The shelves, in the order they are drawn. "Running low" and "Out of stock"
# are computed, not stored: they are a view of the same items.
CATEGORIES = ["Fresh Produce", "Grains", "Dairy & Protein", "Snacks",
              "Beverages", "Household Essentials"]
_CANON = {c.lower(): c for c in CATEGORIES}

# Packaging and marketing words. Stripped so the same product spelled two ways
# collapses to one shelf item; kept short, because over-stripping merges things
# that are genuinely different ("whole milk" vs "oat milk" must not collide).
_NOISE_WORDS = re.compile(
    r"\b(organic|fresh|large|small|value|pack|pk|pkg|ct|count|ea|each|dozen|"
    r"oz|lb|lbs|kg|g|mg|ml|l|lt|ltr|gal|gallon|qt|pt|bag|box|btl|bottle|jar|can|"
    r"family|size|great|brand)\b", re.I)


def slugify(name: str) -> str:
    """Two receipts spell the same thing differently ("Milk, Whole 1 Gal" and
    "WHOLE MILK 1GAL"). Both must land on ONE shelf item, or the forecast sees
    two items bought once each instead of one bought twice, and never learns
    an interval."""
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    # Digits go BEFORE the word list, so "1gal" becomes "gal" and is then
    # recognised as packaging. Stripping words first leaves "1gal" intact and
    # the two spellings never meet.
    s = re.sub(r"\d+", " ", s)
    s = _NOISE_WORDS.sub(" ", s)
    tokens = sorted(set(s.split()))
    return " ".join(tokens)[:120] or re.sub(r"\s+", " ", (name or "").lower()).strip()[:120]


def canonical_category(raw: str) -> str:
    c = (raw or "").strip().lower()
    if c in _CANON:
        return _CANON[c]
    for key, label in _CANON.items():
        if c and (c in key or key.split(" &")[0] in c):
            return label
    return "Household Essentials" if c else ""


def upsert_item(db: Session, *, user_id: str, name: str, category: str = "",
                brand: str = "", size: str = "", unit: str = "",
                image_ref: str = "") -> GroceryItem:
    slug = slugify(name)
    item = db.scalar(select(GroceryItem).where(
        GroceryItem.user_id == user_id, GroceryItem.slug == slug))
    if item is None:
        item = GroceryItem(user_id=user_id, slug=slug, name=name[:120],
                           category=canonical_category(category))
        db.add(item)
        db.flush()
    # Fill blanks, never overwrite: a receipt line should not rename an item
    # the person named themselves.
    for field, value in (("brand", brand), ("size", size), ("unit", unit),
                         ("image_ref", image_ref)):
        if value and not getattr(item, field):
            setattr(item, field, value[:200])
    if category and not item.category:
        item.category = canonical_category(category)
    item.updated_at = utcnow()
    return item


def record_purchase(db: Session, *, user_id: str, item: GroceryItem,
                    purchased_at: datetime, quantity: float = 1.0,
                    source: str = "manual", source_ref: str = "",
                    merchant: str = "", unit_price_cents: int | None = None
                    ) -> GroceryPurchase | None:
    """Idempotent per (source, source_ref, item): re-reading a receipt is not
    a second shopping trip. Returns None when it was already known."""
    existing = db.scalar(select(GroceryPurchase).where(
        GroceryPurchase.user_id == user_id, GroceryPurchase.item_id == item.id,
        GroceryPurchase.source == source, GroceryPurchase.source_ref == (source_ref or "")))
    if existing is not None:
        return None
    when = purchased_at if purchased_at.tzinfo else purchased_at.replace(tzinfo=timezone.utc)
    row = GroceryPurchase(user_id=user_id, item_id=item.id, source=source,
                          source_ref=(source_ref or "")[:120], merchant=merchant[:80],
                          quantity=float(quantity or 1), unit_price_cents=unit_price_cents,
                          purchased_at=when)
    db.add(row)
    last = item.last_purchased_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is None or when > last:
        item.last_purchased_at = when
    # Buying it settles the question of whether they have any.
    item.declared_out_at = None
    item.on_list = False
    item.updated_at = utcnow()
    db.flush()
    return row


def purchases_for(db: Session, user_id: str, item_id: str) -> list[tuple[datetime, float]]:
    rows = db.scalars(select(GroceryPurchase).where(
        GroceryPurchase.user_id == user_id, GroceryPurchase.item_id == item_id)
        .order_by(GroceryPurchase.purchased_at)).all()
    return [(p.purchased_at, p.quantity) for p in rows]


def item_state(db: Session, user_id: str, item: GroceryItem, now=None) -> dict:
    f = forecast(purchases=purchases_for(db, user_id, item.id),
                 category=item.category, last_purchased_at=item.last_purchased_at,
                 declared_out_at=item.declared_out_at, now=now)
    return {
        "id": item.id, "name": item.name, "category": item.category or "Household Essentials",
        "brand": item.brand, "size": item.size, "unit": item.unit,
        "image_ref": item.image_ref, "on_list": item.on_list, "pinned": item.pinned,
        "last_purchased_at": (item.last_purchased_at.isoformat()
                              if item.last_purchased_at else ""),
        **f.as_dict(),
    }


def grocery_context(db: Session, user_id: str) -> dict:
    """The shelf slice of ContextSlice.domain_data — exactly what the screen draws."""
    items = list(db.scalars(select(GroceryItem).where(GroceryItem.user_id == user_id)
                            .order_by(GroceryItem.name)))
    states = [item_state(db, user_id, i) for i in items]

    shelves = []
    for cat in CATEGORIES:
        on_shelf = [s for s in states if s["category"] == cat]
        if on_shelf:
            shelves.append({"category": cat, "items": on_shelf})

    low = sorted([s for s in states if s["status"] == "running_low"],
                 key=lambda s: s["days_left"])
    out = sorted([s for s in states if s["status"] == "out"],
                 key=lambda s: s["days_left"])

    orders = list(db.scalars(select(GroceryOrder).where(
        GroceryOrder.user_id == user_id, GroceryOrder.status.in_(("draft", "confirmed")))
        .order_by(GroceryOrder.created_at.desc()).limit(5)))
    linked = list(db.scalars(select(GroceryLink).where(
        GroceryLink.user_id == user_id, GroceryLink.status == "linked")))

    return {
        "shelves": shelves,
        "running_low": low,
        "out_of_stock": out,
        "list": [s for s in states if s["on_list"]],
        "item_count": len(states),
        # How much of this shelf is built on receipts rather than category
        # guesses. A screen full of "assumed" is a screen that has not earned
        # its predictions yet, and should say so instead of looking confident.
        "measured_count": sum(1 for s in states if s["basis"] in ("measured", "estimated")),
        "platforms": [{"platform": l.platform, "label": l.account_label,
                       "status": l.status} for l in linked],
        "pending_orders": [{"id": o.id, "platform": o.platform, "status": o.status,
                            "lines": o.lines or [], "reason": o.reason,
                            "subtotal_cents": o.subtotal_cents} for o in orders],
    }


def set_declared_out(db: Session, *, user_id: str, item_id: str, out: bool) -> GroceryItem:
    item = db.get(GroceryItem, item_id)
    if item is None or item.user_id != user_id:
        raise ValueError("No such item")
    item.declared_out_at = utcnow() if out else None
    if out:
        item.on_list = True
    item.updated_at = utcnow()
    return item
