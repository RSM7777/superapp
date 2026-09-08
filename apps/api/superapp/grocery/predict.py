"""When will they run out?

The two shelves at the bottom of the screen — Running low, Out of stock — are
this file's output, so it is worth being precise about what it does and does
not know.

It is deterministic arithmetic, not a model call. Three reasons. It runs on
every item on every render, so it has to be free. Its answer has to be
explainable to the person looking at a red shelf ("you buy milk every 6 days
and it has been 8"). And a model asked to guess a repurchase interval will
happily invent one, which is exactly the failure that makes a prediction
feature untrustworthy.

The method: how often does this person actually rebuy this thing? The gaps
between their own purchases are the signal. Before there are any gaps to
measure, a per-category prior stands in — and the answer says so, because
"assumed" and "measured" must never look alike on the shelf.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median

# How long one unit of a category typically lasts one household, in days.
# Deliberately coarse: these exist to be replaced by the person's own gaps as
# soon as there are two of them, not to be accurate on their own.
CATEGORY_DAYS = {
    "fresh produce": 7,
    "dairy & protein": 7,
    "grains": 45,
    "snacks": 14,
    "beverages": 10,
    "household essentials": 45,
}
DEFAULT_DAYS = 21

MIN_DAYS, MAX_DAYS = 1, 365
LOW_FRACTION = 0.25       # inside the last quarter of its life, it is running low
LOW_FLOOR_DAYS = 2        # ...and always at least the last two days

STOCKED, LOW, OUT = "stocked", "running_low", "out"


@dataclass
class Forecast:
    """What we think, and how much of it we actually know."""
    status: str               # stocked | running_low | out
    days_supply: float        # how long one purchase lasts this person
    days_left: float          # negative means overdue
    out_on: datetime | None
    basis: str                # measured | estimated | assumed | declared
    reason: str               # one plain line, shown to the person

    def as_dict(self) -> dict:
        return {"status": self.status, "days_supply": round(self.days_supply, 1),
                "days_left": round(self.days_left, 1), "basis": self.basis,
                "reason": self.reason,
                "out_on": self.out_on.date().isoformat() if self.out_on else ""}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def intervals(purchases: list[tuple[datetime, float]]) -> list[float]:
    """Days between consecutive purchases, divided by how much was bought the
    earlier time.

    The division is the whole trick. Buying two cartons at once does not mean
    the household drinks milk half as often; it means that purchase lasted
    twice as long. Without normalising, a single bulk buy teaches the model
    that this person barely uses the thing.
    """
    ordered = sorted((( _aware(d), max(float(q or 1), 0.1)) for d, q in purchases),
                     key=lambda p: p[0])
    out = []
    for (d0, q0), (d1, _) in zip(ordered, ordered[1:]):
        gap = (d1 - d0).total_seconds() / 86400.0
        if gap <= 0:
            continue          # same-day top-up, not a repurchase cycle
        out.append(gap / q0)
    return out


def days_supply(purchases: list[tuple[datetime, float]], category: str = "") -> tuple[float, str]:
    """How long one unit lasts this person, and how much we actually know.

    - two or more gaps: their own median, `measured`
    - one gap: half theirs, half the prior — one observation is a coincidence
    - none: the category prior, `assumed`
    """
    prior = float(CATEGORY_DAYS.get((category or "").strip().lower(), DEFAULT_DAYS))
    gaps = intervals(purchases)
    if len(gaps) >= 2:
        return _clamp(median(gaps)), "measured"
    if len(gaps) == 1:
        return _clamp((gaps[0] + prior) / 2), "estimated"
    return _clamp(prior), "assumed"


def _clamp(v: float) -> float:
    return max(MIN_DAYS, min(MAX_DAYS, float(v)))


def forecast(*, purchases: list[tuple[datetime, float]], category: str = "",
             last_purchased_at: datetime | None = None,
             declared_out_at: datetime | None = None,
             now: datetime | None = None) -> Forecast:
    """The shelf's verdict for one item.

    `declared_out_at` is the person saying so themselves. It outranks every
    calculation and is never argued with: they can see their own cupboard, and
    an assistant that insists otherwise is not worth having.
    """
    now = _aware(now or datetime.now(timezone.utc))
    supply, basis = days_supply(purchases, category)

    last = last_purchased_at or (max(d for d, _ in purchases) if purchases else None)
    if declared_out_at is not None and (last is None or _aware(declared_out_at) >= _aware(last)):
        return Forecast(status=OUT, days_supply=supply, days_left=0.0, out_on=_aware(declared_out_at),
                        basis="declared", reason="you marked this out")

    if last is None:
        return Forecast(status=STOCKED, days_supply=supply, days_left=supply, out_on=None,
                        basis=basis, reason="never bought through Nano, so nothing to go on")

    last = _aware(last)
    elapsed = (now - last).total_seconds() / 86400.0
    days_left = supply - elapsed
    out_on = last + timedelta(days=supply)
    threshold = max(LOW_FLOOR_DAYS, supply * LOW_FRACTION)

    if days_left <= 0:
        status = OUT
    elif days_left <= threshold:
        status = LOW
    else:
        status = STOCKED

    how = {"measured": f"you rebuy this about every {supply:.0f} days",
           "estimated": f"looks like about every {supply:.0f} days, on one repeat so far",
           "assumed": f"typically lasts about {supply:.0f} days — no repeat from you yet"}[basis]
    if days_left > 0:
        when = "about %.0f days left" % days_left
    elif days_left > -1:
        when = "due about now"
    else:
        when = "overdue by %.0f days" % abs(days_left)
    return Forecast(status=status, days_supply=supply, days_left=days_left, out_on=out_on,
                    basis=basis, reason=f"{how}; {when}")
