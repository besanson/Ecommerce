from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from gacct.domain.product import ProductOffer, RetailerTerms


@dataclass
class RetailerAgent:
    """A simulated retailer-side agent.

    Returns offers from a static catalogue and decides what consumer data it
    would like in order to fulfil. The agent's data requests deliberately
    sometimes exceed what the consumer has whitelisted — the governance layer
    is responsible for catching that. The retailer agent itself does not call
    governance; it cannot.
    """

    retailer_id: str
    display_name: str
    catalogue: List[ProductOffer] = field(default_factory=list)
    requires_data_fields: List[str] = field(
        default_factory=lambda: ["shipping_address", "payment_token_id"]
    )

    def search(self, *, max_results: int = 10) -> List[ProductOffer]:
        return list(self.catalogue[:max_results])

    def offer_substitute(self, original: ProductOffer) -> Optional[ProductOffer]:
        for offer in self.catalogue:
            if offer.sku != original.sku and offer.in_stock:
                return offer.model_copy(update={"substitute_for_offer_id": original.offer_id})
        return None

    def quote_with_shipping_upgrade(
        self, offer: ProductOffer, *, target_days: int, surcharge_eur: float
    ) -> ProductOffer:
        upgraded_terms: RetailerTerms = offer.terms
        return offer.model_copy(
            update={
                "shipping_days": target_days,
                "shipping_eur": offer.shipping_eur + surcharge_eur,
                "terms": upgraded_terms,
            }
        )

    def confirm_order(self, offer: ProductOffer, shared_fields: List[str]) -> Dict[str, object]:
        return {
            "status": "confirmed",
            "retailer_id": self.retailer_id,
            "order_total_eur": offer.total_eur,
            "shared_fields": list(shared_fields),
            "promised_shipping_days": offer.shipping_days,
        }
