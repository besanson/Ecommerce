from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class RetailerTerms(BaseModel):
    """Commercial terms a retailer agent attaches to an offer."""

    return_window_days: int
    free_returns: bool = False
    requires_data_fields: List[str] = Field(
        default_factory=list,
        description="Fields the retailer requests in order to fulfil. May exceed "
        "what the consumer permits; the governance layer is responsible for the "
        "comparison.",
    )
    promotion_code: Optional[str] = None
    promotion_discount_eur: float = 0.0
    cancellation_fee_eur: float = 0.0


class ProductOffer(BaseModel):
    """A single offer surfaced by a retailer agent."""

    offer_id: str
    retailer_id: str
    sku: str
    title: str
    price_eur: float
    shipping_eur: float = 0.0
    shipping_days: int
    materials: List[str] = Field(default_factory=list)
    in_stock: bool = True
    substitute_for_offer_id: Optional[str] = Field(
        default=None,
        description="If set, this offer is being proposed as a substitute for "
        "another offer identified here. Used by substitution policy.",
    )
    terms: RetailerTerms

    @property
    def total_eur(self) -> float:
        return round(self.price_eur + self.shipping_eur - self.terms.promotion_discount_eur, 2)
