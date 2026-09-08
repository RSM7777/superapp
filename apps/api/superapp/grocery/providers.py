"""The platforms themselves.

`ListStore` is the one that always works and never lies: it turns a basket
into a shopping list the person takes to a shop, and it says outright that it
did not order anything.

Walmart and Instacart are declared but not pretended. Neither publishes a
consumer order-placement API a third-party assistant can call on a person's
behalf; their public programmes are for retailers, advertisers and connected
storefronts. So linking them today buys receipt matching and price context,
and `place_order` raises `StoreUnsupported` with a sentence a person can
understand. When a partnership exists, the credential goes in the vault and
`can_order` flips — no caller above this line changes.
"""
from .base import OrderLine, Quote, StoreNotConnected, StoreUnsupported


class ListStore:
    """No platform at all: the basket becomes a list.

    Always available, because a shopping list is something the app can always
    honestly deliver. `can_order` is False, so the UI offers "Add to list",
    never "Place order".
    """

    platform = "list"
    can_order = False

    def quote(self, lines: list[OrderLine]) -> Quote:
        return Quote(platform=self.platform, lines=list(lines),
                     note="A list to shop from. Nano is not buying anything here.")

    def place_order(self, lines: list[OrderLine]) -> str:
        raise StoreUnsupported(
            "This is a shopping list, not a store. Link a platform that can "
            "check out, or shop from the list yourself.")


class _PartnerStore:
    """A real platform, linked for reading and not (yet) for buying."""

    platform = ""
    label = ""
    can_order = False

    def __init__(self, credential: dict | None = None) -> None:
        self.credential = credential or {}
        if not self.credential:
            raise StoreNotConnected(f"{self.label} isn't linked. Link it in settings first.")

    def quote(self, lines: list[OrderLine]) -> Quote:
        # Deliberately no invented prices. An estimate the person mistakes for
        # a real total is worse than no total.
        return Quote(platform=self.platform, lines=list(lines),
                     note=f"{self.label} is linked for receipts and prices. "
                          f"Nano cannot check out there yet.")

    def place_order(self, lines: list[OrderLine]) -> str:
        raise StoreUnsupported(
            f"{self.label} does not offer an ordering API that Nano can use on "
            f"your behalf. Nano can build the basket; you place it in the "
            f"{self.label} app.")


class WalmartStore(_PartnerStore):
    platform = "walmart"
    label = "Walmart"


class InstacartStore(_PartnerStore):
    platform = "instacart"
    label = "Instacart"


PLATFORMS = {
    "list": ("Shopping list", False),
    "walmart": ("Walmart", True),      # True = needs linking
    "instacart": ("Instacart", True),
}
