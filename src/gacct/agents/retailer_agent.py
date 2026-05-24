from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from gacct.domain.product import ProductOffer, RetailerTerms
from gacct.mcp.transport import MCPServer


@dataclass
class RetailerAgent(MCPServer):
    """A simulated retailer-side agent exposed as an MCP server.

    Tools registered:
      list_products(max_results)           -> List[ProductOffer]
      get_terms()                          -> {"requires_data_fields": [...]}
      propose_substitute(original_sku)     -> ProductOffer | None
      quote_shipping_upgrade(sku, days)    -> ProductOffer
      confirm_order(sku, shared_fields)    -> dict

    The retailer is governance-agnostic: it does not import gacct.governance.
    Whether or not a tool is invoked is the consumer-side engine's decision.
    """

    retailer_id: str = ""
    display_name: str = ""
    catalogue: List[ProductOffer] = field(default_factory=list)
    requires_data_fields: List[str] = field(
        default_factory=lambda: ["shipping_address", "payment_token_id"]
    )
    substitute_proposal_probability: float = 0.0
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        # MCPServer.__init__ expects a name; dataclass field gives us retailer_id.
        super().__init__(name=self.retailer_id)
        self._rng = random.Random(self.seed)
        self.register_tool(
            "list_products",
            self._list_products,
            "Return the retailer's current catalogue of in-stock-tagged offers.",
        )
        self.register_tool(
            "get_terms",
            self._get_terms,
            "Return the consumer data fields the retailer requires to fulfil.",
        )
        self.register_tool(
            "propose_substitute",
            self._propose_substitute,
            "Given an original sku, return a substitute offer if one is available, or None.",
        )
        self.register_tool(
            "quote_shipping_upgrade",
            self._quote_shipping_upgrade,
            "Return the offer adjusted for an expedited shipping option.",
        )
        self.register_tool(
            "confirm_order",
            self._confirm_order,
            "Confirm an order. The consumer-side engine wraps this call; if "
            "the governance verdict is not ALLOW the tool is not invoked.",
        )

    # -- tool handlers -----------------------------------------------------

    def _list_products(self, max_results: int = 10, shuffle: bool = False) -> List[ProductOffer]:
        items = list(self.catalogue[:max_results])
        if shuffle:
            self._rng.shuffle(items)
        return items

    def _get_terms(self) -> Dict[str, Any]:
        return {"requires_data_fields": list(self.requires_data_fields)}

    def _propose_substitute(self, original_sku: str) -> Optional[ProductOffer]:
        original = next((o for o in self.catalogue if o.sku == original_sku), None)
        if original is None:
            return None
        alternatives = [o for o in self.catalogue if o.sku != original_sku and o.in_stock]
        if not alternatives:
            return None
        choice = self._rng.choice(alternatives) if self._rng.random() < 1.0 else alternatives[0]
        return choice.model_copy(update={"substitute_for_offer_id": original.offer_id})

    def _quote_shipping_upgrade(self, sku: str, target_days: int, surcharge_eur: float) -> ProductOffer:
        offer = next(o for o in self.catalogue if o.sku == sku)
        return offer.model_copy(
            update={
                "shipping_days": target_days,
                "shipping_eur": offer.shipping_eur + surcharge_eur,
            }
        )

    def _confirm_order(self, sku: str, shared_fields: List[str]) -> Dict[str, Any]:
        offer = next(o for o in self.catalogue if o.sku == sku)
        return {
            "status": "confirmed",
            "retailer_id": self.retailer_id,
            "sku": sku,
            "order_total_eur": offer.total_eur,
            "shared_fields": list(shared_fields),
            "promised_shipping_days": offer.shipping_days,
        }


def offer_from_dict(d: Dict[str, Any]) -> ProductOffer:
    """Convenience for callers that pulled an offer back over the wire as a dict."""

    if "terms" in d and isinstance(d["terms"], dict):
        d = {**d, "terms": RetailerTerms.model_validate(d["terms"])}
    return ProductOffer.model_validate(d)
