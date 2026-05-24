from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ConsumerProfile(BaseModel):
    """Identity and standing consent of the human principal."""

    consumer_id: str
    display_name: str
    shipping_country: str
    payment_token_id: str = Field(
        description="Opaque reference to a payment instrument. The token itself "
        "is not transmitted by the consumer agent; only the reference is."
    )
    permitted_data_fields: List[str] = Field(
        default_factory=lambda: ["shipping_address", "payment_token_id"],
        description="Exhaustive list of consumer data fields the consumer agent "
        "may share with retailers. Anything outside this list must be blocked.",
    )


class ShoppingDelegation(BaseModel):
    """The bounded authority the consumer hands to the consumer agent.

    This object is the source of truth for delegated authority. Policy packs
    are evaluated against the facts captured here.
    """

    delegation_id: str
    consumer_id: str
    mission: str = Field(
        description="Human-readable shopping mission, e.g. 'half marathon shoes'."
    )
    budget_ceiling_eur: float
    auto_buy_threshold_eur: float = Field(
        description="At or below this amount the agent may complete a purchase "
        "without human approval. Above it the action must ESCALATE."
    )
    approved_retailers: List[str]
    denied_retailers: List[str] = Field(default_factory=list)
    forbidden_materials: List[str] = Field(default_factory=list)
    substitution_tolerance_pct: float = Field(
        description="Maximum allowed price variance for an accepted substitute, "
        "expressed as a fraction (0.10 == 10%)."
    )
    delivery_deadline_days: int
    min_return_window_days: int
    permitted_data_fields: List[str]
    notes: Optional[str] = None

    @property
    def acting_on_behalf_of(self) -> str:
        return self.consumer_id
