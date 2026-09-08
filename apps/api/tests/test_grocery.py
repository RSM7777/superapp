"""The grocery vertical.

Two things get most of the attention here, because they are the two that would
actually hurt someone: the forecast that drives the red shelf, and the gate
between "Nano built a basket" and "money left your account".
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

# The app's engine is installed exactly once, by test_spine. Standing up a
# second in-memory SQLite engine here would split the app's session from this
# module's: `client` would write to one database and `SessionLocal` would read
# an empty other one, and the tests would pass alone and fail as a suite.
from test_spine import AUTH, SessionLocal, client

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


# --- the forecast ----------------------------------------------------------

def test_repeat_purchases_beat_the_category_guess():
    """The whole point: a household's own rhythm outranks an average. Someone
    who rebuys milk every 6 days should not be told it lasts a week."""
    from superapp.grocery.predict import forecast

    buys = [(NOW - timedelta(days=d), 1) for d in (24, 18, 12, 6)]
    f = forecast(purchases=buys, category="Dairy & Protein", now=NOW)
    assert f.basis == "measured"
    assert 5.5 <= f.days_supply <= 6.5
    # Six days of supply bought six days ago: due now, not next week.
    assert f.status == "out"

    cold = forecast(purchases=[], category="Dairy & Protein", now=NOW)
    assert cold.basis == "assumed" and cold.status == "stocked"


def test_buying_two_does_not_teach_a_slower_household():
    """Buying two cartons at once means that trip lasted twice as long, not
    that they drink half as much. Without normalising by quantity a single
    bulk buy poisons the interval for good."""
    from superapp.grocery.predict import intervals

    d0 = NOW - timedelta(days=20)
    d1 = NOW - timedelta(days=6)          # 14 days later, but 2 units were bought
    assert intervals([(d0, 2), (d1, 1)]) == [7.0]
    assert intervals([(d0, 1), (d1, 1)]) == [14.0]


def test_the_person_outranks_the_prediction():
    """They can see their own cupboard. An assistant that argues is worthless."""
    from superapp.grocery.predict import forecast

    just_bought = [(NOW - timedelta(days=1), 1)]
    confident = forecast(purchases=just_bought, category="Grains", now=NOW)
    assert confident.status == "stocked"

    declared = forecast(purchases=just_bought, category="Grains", now=NOW,
                        declared_out_at=NOW)
    assert declared.status == "out" and declared.basis == "declared"
    assert "you marked this out" in declared.reason


def test_forecast_never_returns_an_absurd_shelf_life():
    """Two purchases minutes apart would otherwise imply a supply of hours,
    and every item would live permanently on the red shelf."""
    from superapp.grocery.predict import MAX_DAYS, MIN_DAYS, days_supply

    frantic = [(NOW - timedelta(minutes=30), 1), (NOW, 1)]
    supply, _ = days_supply(frantic, "Snacks")
    assert supply >= MIN_DAYS

    glacial = [(NOW - timedelta(days=4000), 1), (NOW, 1)]
    supply, _ = days_supply(glacial, "Grains")
    assert supply <= MAX_DAYS


# --- the shelf -------------------------------------------------------------

def test_two_spellings_of_one_product_land_on_one_shelf_item():
    """Receipts spell things differently. If they do not collapse, the forecast
    sees two items bought once each and never learns an interval at all."""
    from superapp.substrate.grocery import upsert_item

    db = SessionLocal()
    a = upsert_item(db, user_id="g1", name="Milk, Whole 1 Gal", category="Dairy & Protein")
    b = upsert_item(db, user_id="g1", name="WHOLE MILK 1GAL")
    db.commit()
    assert a.id == b.id
    # ...but genuinely different things stay apart.
    oat = upsert_item(db, user_id="g1", name="Oat Milk")
    db.commit()
    assert oat.id != a.id
    db.close()


def test_reading_the_same_receipt_twice_is_not_two_shopping_trips():
    """A duplicated purchase halves the measured interval and puts a stocked
    item on the red shelf."""
    from superapp.models import GroceryPurchase
    from superapp.substrate.grocery import record_purchase, upsert_item

    db = SessionLocal()
    item = upsert_item(db, user_id="g2", name="Rice", category="Grains")
    first = record_purchase(db, user_id="g2", item=item, purchased_at=NOW,
                            source="email", source_ref="receipt-1")
    again = record_purchase(db, user_id="g2", item=item, purchased_at=NOW,
                            source="email", source_ref="receipt-1")
    db.commit()
    assert first is not None and again is None
    assert db.scalar(select(GroceryPurchase).where(
        GroceryPurchase.user_id == "g2")) is not None
    assert len(db.scalars(select(GroceryPurchase).where(
        GroceryPurchase.user_id == "g2")).all()) == 1
    db.close()


def test_shelf_state_splits_out_the_two_computed_shelves():
    """Running low and Out of stock are views of the same items, and an item
    on one of them must not also sit on its category shelf twice."""
    from superapp.substrate.grocery import grocery_context, record_purchase, upsert_item

    db = SessionLocal()
    uid = "g3"
    milk = upsert_item(db, user_id=uid, name="Milk", category="Dairy & Protein")
    for d in (21, 14, 7):
        record_purchase(db, user_id=uid, item=milk, purchased_at=NOW - timedelta(days=d),
                        source="email", source_ref=f"r{d}")
    rice = upsert_item(db, user_id=uid, name="Basmati Rice", category="Grains")
    record_purchase(db, user_id=uid, item=rice, purchased_at=NOW - timedelta(days=1),
                    source="email", source_ref="r-rice")
    db.commit()

    state = grocery_context(db, uid)
    names_out = {s["name"] for s in state["out_of_stock"]}
    assert "Milk" in names_out, "bought every 7 days, last bought 7 days ago"
    assert "Basmati Rice" not in names_out
    assert state["item_count"] == 2
    assert state["measured_count"] >= 1
    # Every item still belongs to exactly one category shelf.
    shelved = [i["id"] for s in state["shelves"] for i in s["items"]]
    assert len(shelved) == len(set(shelved)) == 2
    db.close()


# --- the money gate --------------------------------------------------------

AUTH_UID = "harshith"   # who the dev bearer token authenticates as


def _basket(label):
    """A draft basket belonging to the authenticated user, via the API.

    Seeded under AUTH_UID rather than a per-test id: the endpoint builds the
    basket for whoever the token says, so seeding anyone else produces an
    empty one and the test passes for the wrong reason.
    """
    from superapp.substrate.grocery import record_purchase, upsert_item

    db = SessionLocal()
    item = upsert_item(db, user_id=AUTH_UID, name=f"Coffee {label}", category="Beverages")
    record_purchase(db, user_id=AUTH_UID, item=item,
                    purchased_at=NOW - timedelta(days=400),
                    source="email", source_ref=f"old-{label}")
    db.commit(); db.close()
    r = client.post("/v1/grocery/basket", headers=AUTH, json={"platform": "list"})
    assert r.status_code == 200, r.text
    order = r.json()["order"]
    assert order is not None, "seeded item should be long overdue"
    return order


def test_placing_an_order_requires_a_human_yes():
    """Nano may fill a basket. It may never buy it. This is the gate."""
    order = _basket("g-order")
    r = client.post(f"/v1/grocery/orders/{order['id']}/place", headers=AUTH)
    assert r.status_code == 403
    assert "never buys on its own" in r.json()["detail"]


def test_a_yes_covers_the_basket_it_was_given_for_and_nothing_else():
    """Approving 'milk and eggs' must not become authority to buy whatever the
    basket happens to contain later."""
    order = _basket("g-order2")
    ok = client.post(f"/v1/grocery/orders/{order['id']}/confirm", headers=AUTH,
                     json={"fingerprint": order["fingerprint"]})
    assert ok.status_code == 200 and ok.json()["order"]["confirmed_by"] == "user"

    # Something changes the basket after the yes.
    from superapp.models import GroceryOrder
    db = SessionLocal()
    o = db.get(GroceryOrder, order["id"])
    o.lines = (o.lines or []) + [{"item_id": "x", "name": "Champagne", "quantity": 12}]
    db.commit(); db.close()

    stale = client.post(f"/v1/grocery/orders/{order['id']}/confirm", headers=AUTH,
                        json={"fingerprint": order["fingerprint"]})
    assert stale.status_code == 409
    assert "changed since you looked" in stale.json()["detail"]


def test_a_store_that_cannot_order_says_so_instead_of_inventing_an_id():
    """The mail seam's worst bug, ported: a client with no way to act used to
    return a plausible id and report success. Here that costs real groceries."""
    order = _basket("g-order3")
    client.post(f"/v1/grocery/orders/{order['id']}/confirm", headers=AUTH,
                json={"fingerprint": order["fingerprint"]})
    r = client.post(f"/v1/grocery/orders/{order['id']}/place", headers=AUTH)
    assert r.status_code == 422, "a platform that cannot check out is not a server error"
    assert "shopping list, not a store" in r.json()["detail"]

    from superapp.models import GroceryOrder
    db = SessionLocal()
    o = db.get(GroceryOrder, order["id"])
    assert o.status == "failed" and not o.external_id, "no id was invented"
    db.close()


def test_money_is_tier_three_and_has_no_autonomous_path():
    """Not a route test: the policy table itself. Every provenance is refused,
    so no cron, rule or spoken command can reach a charge."""
    from superapp.policy import assess

    for provenance in ("user", "email", "system"):
        v = assess("grocery.place_order", provenance=provenance)
        assert v.allowed is False and v.tier == 3
    assert assess("grocery.build_basket", provenance="system").allowed is True


def test_linked_platforms_never_advertise_ordering_they_cannot_do():
    """Neither Walmart nor Instacart exposes a consumer ordering API a third
    party can call. The API must not imply otherwise, or the UI will draw a
    button that spends nothing and disappoints someone."""
    client.post("/v1/grocery/platforms/link", headers=AUTH,
                json={"platform": "walmart", "account_label": "rohit@example.com"})
    rows = {p["platform"]: p for p in client.get("/v1/grocery/platforms",
                                                 headers=AUTH).json()["platforms"]}
    assert rows["walmart"]["linked"] is True
    assert all(p["can_order"] is False for p in rows.values())

    from superapp.grocery.base import StoreUnsupported
    from superapp.grocery.factory import client_for
    db = SessionLocal()
    store = client_for(db, "harshith", "walmart")
    with pytest.raises(StoreUnsupported):
        store.place_order([])
    db.close()


def test_an_unlinked_platform_raises_rather_than_falling_back_to_the_list():
    """"I added it to your list" when someone asked to order is a different
    outcome, and they have to be told which one happened."""
    from superapp.grocery.base import StoreNotConnected
    from superapp.grocery.factory import client_for

    db = SessionLocal()
    with pytest.raises(StoreNotConnected):
        client_for(db, "nobody-linked-this", "instacart")
    db.close()


# --- the screen ------------------------------------------------------------

def test_shelf_screen_renders_and_explains_itself():
    from superapp.agents.base import render_screen
    from superapp.substrate.grocery import record_purchase, upsert_item

    db = SessionLocal()
    uid = "g-render"
    item = upsert_item(db, user_id=uid, name="Doritos", category="Snacks")
    for d in (40, 26, 12):
        record_purchase(db, user_id=uid, item=item, purchased_at=NOW - timedelta(days=d),
                        source="email", source_ref=f"d{d}")
    db.commit()
    screen = render_screen(db, agent="grocery", user_id=uid)
    blocks = [b for s in screen.sections for b in s.blocks]
    kinds = {b.type for b in blocks}
    assert "shelf" in kinds
    shelf = next(b for b in blocks if b.type == "shelf")
    assert any(s.label == "Snacks" for s in shelf.shelves)
    # Whatever the verdict, the person can see the reasoning behind it.
    if any(s.tone in ("amber", "rose") for s in shelf.shelves):
        assert "list" in kinds, "a red shelf must come with its reasons"
    db.close()


def test_empty_shelf_offers_the_receipt_path_not_a_catalogue():
    from superapp.agents.base import render_screen

    db = SessionLocal()
    screen = render_screen(db, agent="grocery", user_id="g-empty")
    text = " ".join(b.text for s in screen.sections for b in s.blocks
                    if b.type == "text")
    assert "receipts" in text.lower()
    db.close()
