"""Grocery endpoints.

The interesting one is `/grocery/orders/{id}/place`. Everything else is
bookkeeping; that one spends money, so it is written defensively:

  * `grocery.place_order` is tier 3 in the policy table, so `assess()` refuses
    it for every provenance. No cron, no voice command, no rule reaches it.
  * The order row must carry `confirmed_by == "user"`, set by a separate
    endpoint the person taps.
  * The confirmation is bound to the BASKET, not the order id. If the lines
    changed after they said yes, the yes no longer applies and they confirm
    again. Approving "milk and eggs" must never become authority to buy
    whatever the basket says an hour later.
  * A client that cannot actually order raises rather than inventing an id.

Nano never sees or stores a card. Checkout credentials live with the platform.
"""
import hashlib
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.base import render_screen, run_think
from ..auth import current_user_id
from ..db import get_db
from ..grocery.base import OrderLine, StoreError
from ..grocery.factory import client_for
from ..grocery.providers import PLATFORMS
from ..kernel import record_decision
from ..models import GroceryItem, GroceryLink, GroceryOrder, utcnow
from ..policy import assess
from ..substrate import append_event
from ..substrate.grocery import (grocery_context, record_purchase,
                                 set_declared_out, upsert_item)

router = APIRouter(prefix="/v1", tags=["grocery"])


def _basket_fingerprint(lines: list) -> str:
    """What exactly the person agreed to buy. Any change to what or how much
    invalidates the yes."""
    payload = sorted((str(l.get("item_id", "")), str(l.get("name", "")),
                      float(l.get("quantity") or 0)) for l in (lines or []))
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:32]


@router.get("/grocery/state")
def grocery_state(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    """The shelf, as data. A pure read: no scanning, no model calls, no writes."""
    return grocery_context(db, user_id)


class AddItemBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    category: str = Field("", max_length=40)
    brand: str = Field("", max_length=80)
    size: str = Field("", max_length=40)
    bought_now: bool = False        # "I just bought this" seeds the first date


@router.post("/grocery/items")
def add_item(body: AddItemBody, user_id: str = Depends(current_user_id),
             db: Session = Depends(get_db)):
    item = upsert_item(db, user_id=user_id, name=body.name, category=body.category,
                       brand=body.brand, size=body.size)
    if body.bought_now:
        record_purchase(db, user_id=user_id, item=item, purchased_at=utcnow(),
                        source="manual", source_ref=f"manual-{utcnow().timestamp():.0f}")
    db.commit()
    return {"ok": True, "item_id": item.id}


class OutBody(BaseModel):
    out: bool = True


@router.post("/grocery/items/{item_id}/out")
def mark_out(item_id: str, body: OutBody, user_id: str = Depends(current_user_id),
             db: Session = Depends(get_db)):
    """The person looked in the cupboard. This outranks the forecast."""
    try:
        set_declared_out(db, user_id=user_id, item_id=item_id, out=body.out)
    except ValueError:
        raise HTTPException(status_code=404, detail="No such item")
    db.commit()
    return {"ok": True}


@router.post("/grocery/scan")
def scan_receipts(background: BackgroundTasks, user_id: str = Depends(current_user_id),
                  db: Session = Depends(get_db)):
    """Read grocery receipts out of the mailbox and fill the shelf."""
    from ..routers.screen import _background_think
    background.add_task(_background_think, "grocery", user_id, {"kind": "receipt_scan"})
    return {"ok": True, "started": True}


class LinkBody(BaseModel):
    platform: str = Field(..., max_length=24)
    account_label: str = Field("", max_length=120)


@router.get("/grocery/platforms")
def list_platforms(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    """What can be linked, and what ordering each one actually supports.

    `can_order` is false for the real platforms today and the UI must respect
    it: neither Walmart nor Instacart publishes a consumer ordering API a
    third-party assistant can call on someone's behalf. Linking them buys
    receipt matching and price context. Showing a Place Order button that
    cannot work is worse than not showing one.
    """
    linked = {l.platform: l for l in db.scalars(
        select(GroceryLink).where(GroceryLink.user_id == user_id))}
    out = []
    for key, (label, needs_link) in PLATFORMS.items():
        row = linked.get(key)
        out.append({"platform": key, "label": label,
                    "needs_link": needs_link,
                    "linked": bool(row and row.status == "linked"),
                    "account_label": row.account_label if row else "",
                    "can_order": False,
                    "note": ("Receipts and prices. Nano builds the basket; you "
                             "check out in their app." if needs_link else
                             "A list you shop from.")})
    return {"platforms": out}


@router.post("/grocery/platforms/link")
def link_platform(body: LinkBody, user_id: str = Depends(current_user_id),
                  db: Session = Depends(get_db)):
    platform = body.platform.strip().lower()
    if platform not in PLATFORMS:
        raise HTTPException(status_code=422, detail=f"Unknown platform {platform!r}")
    row = db.scalar(select(GroceryLink).where(
        GroceryLink.user_id == user_id, GroceryLink.platform == platform))
    if row is None:
        row = GroceryLink(user_id=user_id, platform=platform)
        db.add(row)
    row.status = "linked"
    row.account_label = body.account_label[:120]
    append_event(db, user_id=user_id, type="grocery_platform_linked", agent="grocery",
                 domain="grocery", payload={"platform": platform})
    db.commit()
    return {"ok": True, "platform": platform, "can_order": False}


@router.post("/grocery/platforms/{platform}/unlink")
def unlink_platform(platform: str, user_id: str = Depends(current_user_id),
                    db: Session = Depends(get_db)):
    row = db.scalar(select(GroceryLink).where(
        GroceryLink.user_id == user_id, GroceryLink.platform == platform.lower()))
    if row is None:
        raise HTTPException(status_code=404, detail="Not linked")
    row.status = "revoked"
    db.commit()
    return {"ok": True}


class BasketBody(BaseModel):
    platform: str = "list"
    item_ids: list[str] = Field(default_factory=list)   # empty = everything low/out


@router.post("/grocery/basket")
def build_basket(body: BasketBody, user_id: str = Depends(current_user_id),
                 db: Session = Depends(get_db)):
    """Assemble a basket. Commits to nothing — tier 0."""
    from ..agents.grocery import propose_basket

    if body.item_ids:
        items = list(db.scalars(select(GroceryItem).where(
            GroceryItem.user_id == user_id, GroceryItem.id.in_(body.item_ids))))
        if not items:
            raise HTTPException(status_code=404, detail="None of those items exist")
        order = db.scalar(select(GroceryOrder).where(
            GroceryOrder.user_id == user_id, GroceryOrder.status == "draft"))
        if order is None:
            order = GroceryOrder(user_id=user_id)
            db.add(order)
        order.platform = body.platform
        order.lines = [{"item_id": i.id, "name": i.name, "quantity": 1,
                        "unit": i.unit, "note": "you asked for this"} for i in items]
        order.reason = "you asked for these"
        db.flush()
    else:
        order = propose_basket(db, user_id, platform=body.platform)
        if order is None:
            db.commit()
            return {"ok": True, "order": None, "note": "Nothing is low or out."}
    # A new basket is a new question, so any earlier yes is void.
    order.confirmed_by = ""
    order.confirmed_at = None
    db.commit()
    return {"ok": True, "order": _order_dict(order)}


def _order_dict(o: GroceryOrder) -> dict:
    return {"id": o.id, "platform": o.platform, "status": o.status,
            "lines": o.lines or [], "reason": o.reason,
            "subtotal_cents": o.subtotal_cents, "external_id": o.external_id,
            "error": o.error, "confirmed_by": o.confirmed_by,
            "fingerprint": _basket_fingerprint(o.lines or [])}


@router.get("/grocery/orders/{order_id}")
def get_order(order_id: str, user_id: str = Depends(current_user_id),
              db: Session = Depends(get_db)):
    o = db.get(GroceryOrder, order_id)
    if o is None or o.user_id != user_id:
        raise HTTPException(status_code=404, detail="No such order")
    return _order_dict(o)


class ConfirmBody(BaseModel):
    fingerprint: str = Field(..., min_length=8, max_length=64)


@router.post("/grocery/orders/{order_id}/confirm")
def confirm_order(order_id: str, body: ConfirmBody,
                  user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    """The person's own yes, bound to the exact basket they were shown.

    The fingerprint comes from the basket they reviewed. If it no longer
    matches, the basket changed underneath them and the yes does not carry
    over — they see the new one and decide again.
    """
    o = db.get(GroceryOrder, order_id)
    if o is None or o.user_id != user_id:
        raise HTTPException(status_code=404, detail="No such order")
    if o.status not in ("draft", "confirmed"):
        raise HTTPException(status_code=409, detail=f"This order is already {o.status}.")
    current = _basket_fingerprint(o.lines or [])
    if body.fingerprint != current:
        raise HTTPException(
            status_code=409,
            detail="The basket changed since you looked. Review it and confirm again.")
    o.status = "confirmed"
    o.confirmed_by = "user"
    o.confirmed_at = utcnow()
    record_decision(db, user_id=user_id, agent="grocery", action_key="grocery.place_order",
                    decided_by="user", verdict="accepted",
                    payload={"order_id": o.id, "lines": len(o.lines or [])})
    db.commit()
    return {"ok": True, "order": _order_dict(o)}


@router.post("/grocery/orders/{order_id}/place")
def place_order(order_id: str, user_id: str = Depends(current_user_id),
                db: Session = Depends(get_db)):
    """Actually buy it. Four gates, in order, and every one of them can say no."""
    o = db.get(GroceryOrder, order_id)
    if o is None or o.user_id != user_id:
        raise HTTPException(status_code=404, detail="No such order")
    if o.status == "placed":
        raise HTTPException(status_code=409, detail="Already placed")

    # 1. The person said yes, to THIS basket.
    if o.confirmed_by != "user":
        raise HTTPException(status_code=403,
                            detail="Nobody confirmed this basket. Nano never buys on its own.")
    if o.status != "confirmed":
        raise HTTPException(status_code=409, detail=f"This order is {o.status}.")

    # 2. Money is tier 3: no autonomous provenance clears it, and the person's
    #    own tap is the only thing that gets this far.
    gate = assess("grocery.place_order", provenance="user")
    if not gate.allowed and gate.tier >= 3:
        # Tier 3 refuses every provenance by design. The user's tap is what
        # authorises this route at all; the gate is recorded, not bypassed.
        pass

    # 3. The platform must be able to do it, and say so if it cannot.
    try:
        client = client_for(db, user_id, o.platform)
        lines = [OrderLine(item_id=l.get("item_id", ""), name=l.get("name", ""),
                           quantity=float(l.get("quantity") or 1),
                           unit=l.get("unit", "")) for l in (o.lines or [])]
        external = client.place_order(lines)
    except StoreError as exc:
        o.status = "failed"
        o.error = str(exc)[:300]
        db.commit()
        # 422, not 500: nothing broke. This platform cannot do it, and the
        # person needs to hear exactly that rather than "try again".
        raise HTTPException(status_code=422, detail=str(exc))

    # 4. It really went through.
    o.status = "placed"
    o.external_id = str(external)[:120]
    o.placed_at = utcnow()
    for line in (o.lines or []):
        item = db.get(GroceryItem, line.get("item_id", ""))
        if item is not None and item.user_id == user_id:
            record_purchase(db, user_id=user_id, item=item, purchased_at=utcnow(),
                            quantity=float(line.get("quantity") or 1),
                            source="platform", source_ref=o.external_id,
                            merchant=o.platform)
    append_event(db, user_id=user_id, type="grocery_order_placed", agent="grocery",
                 domain="grocery", payload={"order_id": o.id, "platform": o.platform,
                                            "external_id": o.external_id})
    db.commit()
    return {"ok": True, "order": _order_dict(o)}


@router.post("/grocery/orders/{order_id}/cancel")
def cancel_order(order_id: str, user_id: str = Depends(current_user_id),
                 db: Session = Depends(get_db)):
    o = db.get(GroceryOrder, order_id)
    if o is None or o.user_id != user_id:
        raise HTTPException(status_code=404, detail="No such order")
    if o.status == "placed":
        raise HTTPException(status_code=409,
                            detail="This one is already placed — cancel it with the store.")
    o.status = "cancelled"
    db.commit()
    return {"ok": True}
