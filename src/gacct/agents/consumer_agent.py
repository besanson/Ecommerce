from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from gacct.agents.retailer_agent import RetailerAgent
from gacct.domain.actions import ActionType, ProposedAction
from gacct.domain.consumer import ShoppingDelegation
from gacct.domain.product import ProductOffer
from gacct.governance.engine import GovernanceEngine, GovernedOutcome
from gacct.mcp.transport import MCPTransport
from gacct.reasoning.engine import ConsumerAgentReasoner, Thought


@dataclass
class ConsumerAgent:
    """A simulated personal shopping agent.

    Three responsibilities, kept separate:
      * **Reasoning** — a `ConsumerAgentReasoner` produces thoughts based on
        the delegation and incoming facts. Reasoning never has authority to
        act; it informs which `ProposedAction` to construct next.
      * **Agent-to-agent communication** — an `MCPTransport` carries calls to
        retailer-side tools. Every request and response is logged as an MCP
        message and persisted to the trace.
      * **Action** — every consequential operation is wrapped in
        `engine.govern(...)`. The consumer agent does *not* call retailer
        side effects directly; it passes the MCP call as a `side_effect`
        callable into the engine, and the engine decides whether to invoke it.
    """

    name: str
    delegation: ShoppingDelegation
    engine: GovernanceEngine
    transport: MCPTransport
    reasoner: ConsumerAgentReasoner
    on_thought: Optional[Callable[[Thought], None]] = None

    # -- thought emission --------------------------------------------------

    def _emit_thoughts(self, thoughts: List[Thought]) -> None:
        if not self.on_thought:
            return
        for t in thoughts:
            self.on_thought(t)

    # -- MCP helpers -------------------------------------------------------

    def _mcp(self, retailer: RetailerAgent, method: str, **params):
        return self.transport.call(
            sender=self.name,
            receiver=retailer.retailer_id,
            method=method,
            params=params,
        )

    # -- Governed actions --------------------------------------------------

    def select_merchant(self, *, scenario_id: str, retailer_id: str) -> GovernedOutcome:
        self._emit_thoughts(self.reasoner.think_about_merchant(retailer_id))
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
        self._emit_thoughts(self.reasoner.think_about_data_request(fields))
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
        self._emit_thoughts(self.reasoner.think_about_substitute(original, substitute))
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
        self._emit_thoughts(self.reasoner.think_about_return_terms(offer))
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
        # The side_effect is an MCP call: the engine decides whether to invoke it.
        def _confirm(_a):
            return self._mcp(retailer, "confirm_order", sku=offer.sku, shared_fields=shared_fields)
        return self.engine.govern(
            scenario_id=scenario_id,
            delegation=self.delegation,
            action=action,
            offer=offer,
            requested_data_fields=shared_fields,
            side_effect=_confirm,
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

    # -- High-level reasoning helpers -------------------------------------

    def discover_offers(self, retailer: RetailerAgent, *, shuffle: bool = False) -> List[ProductOffer]:
        """Query a retailer for offers and reason about them. Not a governed
        action; this is pure agent-to-agent communication.
        """

        self._emit_thoughts(self.reasoner.think_about_mission())
        offers: List[ProductOffer] = self._mcp(retailer, "list_products", max_results=10, shuffle=shuffle)
        self._emit_thoughts(self.reasoner.think_about_offers(offers))
        return offers
