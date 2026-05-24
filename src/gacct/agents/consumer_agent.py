from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional

from gacct.agents.retailer_agent import RetailerAgent
from gacct.domain.actions import ActionType, ProposedAction
from gacct.domain.consumer import ShoppingDelegation
from gacct.domain.product import ProductOffer
from gacct.governance.engine import GovernanceEngine, GovernedOutcome


@dataclass
class ConsumerAgent:
    """A simulated personal shopping agent.

    The agent's contract: every consequential step is proposed via the
    governance engine. There is no direct path to retailer side effects.
    Reasoning over offers (filtering, ranking) is intentionally outside the
    governance boundary — only the action of acting on a choice is governed.
    """

    name: str
    delegation: ShoppingDelegation
    engine: GovernanceEngine

    # -- Pure cognition (not governed) -------------------------------------

    def shortlist(self, offers: List[ProductOffer]) -> List[ProductOffer]:
        """Local ranking heuristic. Not governed: nothing leaves the agent.

        The agent applies its own feasibility filter (forbidden materials, in
        stock) before ranking. This is a courtesy, not a control: the same
        constraints are independently enforced by the materials policy pack
        at action time, so a buggy or adversarial agent cannot bypass them.
        """

        forbidden = {m.lower() for m in self.delegation.forbidden_materials}
        feasible = [
            o for o in offers
            if o.in_stock and not (set(m.lower() for m in o.materials) & forbidden)
        ]
        return sorted(feasible, key=lambda o: (o.total_eur, o.shipping_days))

    # -- Governed action wrappers ------------------------------------------

    def select_merchant(self, *, scenario_id: str, retailer_id: str) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.SELECT_MERCHANT,
            payload={"retailer_id": retailer_id},
            reversible=True,
            rationale=f"selecting retailer {retailer_id}",
        )
        return self.engine.govern(
            scenario_id=scenario_id,
            delegation=self.delegation,
            action=action,
        )

    def share_consumer_data(
        self, *, scenario_id: str, retailer: RetailerAgent, fields: List[str]
    ) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.SHARE_CONSUMER_DATA,
            payload={"retailer_id": retailer.retailer_id, "fields": list(fields)},
            reversible=False,
            rationale=f"sharing {fields} with {retailer.retailer_id}",
        )
        return self.engine.govern(
            scenario_id=scenario_id,
            delegation=self.delegation,
            action=action,
            requested_data_fields=fields,
        )

    def accept_substitute(
        self,
        *,
        scenario_id: str,
        substitute: ProductOffer,
        original: ProductOffer,
    ) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.ACCEPT_SUBSTITUTE,
            payload={
                "substitute_sku": substitute.sku,
                "original_sku": original.sku,
                "substitute_price_eur": substitute.price_eur,
                "original_price_eur": original.price_eur,
            },
            reversible=True,
            rationale="retailer offered a substitute SKU",
        )
        return self.engine.govern(
            scenario_id=scenario_id,
            delegation=self.delegation,
            action=action,
            offer=substitute,
            original_offer=original,
        )

    def accept_return_terms(
        self, *, scenario_id: str, offer: ProductOffer
    ) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.ACCEPT_RETURN_TERMS,
            payload={"return_window_days": offer.terms.return_window_days},
            reversible=True,
            rationale="confirming retailer's return terms",
        )
        return self.engine.govern(
            scenario_id=scenario_id,
            delegation=self.delegation,
            action=action,
            offer=offer,
        )

    def apply_promotion(
        self,
        *,
        scenario_id: str,
        offer: ProductOffer,
        discount_eur: float,
        requires_data_fields: Optional[List[str]] = None,
        condition_check=None,
    ) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.APPLY_PROMOTION,
            payload={
                "discount_eur": discount_eur,
                "requires_data_fields": list(requires_data_fields or []),
                "sku": offer.sku,
            },
            reversible=True,
            rationale=f"applying promotion saving {discount_eur:.2f} EUR",
        )
        return self.engine.govern(
            scenario_id=scenario_id,
            delegation=self.delegation,
            action=action,
            offer=offer,
            condition_check=condition_check,
        )

    def upgrade_shipping(
        self, *, scenario_id: str, upgraded_offer: ProductOffer
    ) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.UPGRADE_SHIPPING,
            payload={
                "sku": upgraded_offer.sku,
                "target_shipping_days": upgraded_offer.shipping_days,
                "new_total_eur": upgraded_offer.total_eur,
            },
            reversible=True,
            rationale="upgrading shipping to meet delivery deadline",
        )
        return self.engine.govern(
            scenario_id=scenario_id,
            delegation=self.delegation,
            action=action,
            offer=upgraded_offer,
        )

    def place_order(
        self,
        *,
        scenario_id: str,
        retailer: RetailerAgent,
        offer: ProductOffer,
        shared_fields: List[str],
    ) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.PLACE_ORDER,
            payload={
                "retailer_id": retailer.retailer_id,
                "sku": offer.sku,
                "total_eur": offer.total_eur,
                "shared_fields": list(shared_fields),
            },
            reversible=False,
            rationale="placing order for shortlisted offer",
        )
        return self.engine.govern(
            scenario_id=scenario_id,
            delegation=self.delegation,
            action=action,
            offer=offer,
            requested_data_fields=shared_fields,
            side_effect=lambda _a: retailer.confirm_order(offer, shared_fields),
        )

    def use_payment_token(
        self,
        *,
        scenario_id: str,
        amount_eur: float,
        retailer_id: str,
    ) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.USE_PAYMENT_TOKEN,
            payload={"amount_eur": amount_eur, "retailer_id": retailer_id},
            reversible=False,
            rationale="charging payment token after order confirmation",
        )
        return self.engine.govern(
            scenario_id=scenario_id,
            delegation=self.delegation,
            action=action,
        )
