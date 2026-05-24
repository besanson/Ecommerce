from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from gacct.agents.retailer_agent import RetailerAgent
from gacct.agents.subscription_service import SubscriptionServiceAgent
from gacct.domain.actions import ActionType, ProposedAction
from gacct.domain.consumer import ShoppingDelegation
from gacct.domain.context import ConsumerContext, DataContextValidator
from gacct.domain.decisions import Decision, DecisionRecord
from gacct.domain.product import ProductOffer
from gacct.governance.engine import GovernanceEngine, GovernedOutcome
from gacct.governance.pag import PAGOutcome
from gacct.mcp.transport import MCPTransport
from gacct.policy.evaluator import EvaluationContext
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
    # Optional data foundation (pillar 2). When supplied, every governed
    # action carries context_id + context_version and is pre-screened by
    # the DataContextValidator before reaching PAG.
    context: Optional[ConsumerContext] = None
    context_validator: Optional[DataContextValidator] = None
    on_context_block: Optional[Callable[[DecisionRecord], None]] = None

    # -- thought emission --------------------------------------------------

    def _emit_thoughts(self, thoughts: List[Thought]) -> None:
        if not self.on_thought:
            return
        for t in thoughts:
            self.on_thought(t)

    # -- MCP helpers -------------------------------------------------------

    def _mcp(self, server, method: str, **params):
        """Send an MCP request to any registered server (retailer or
        subscription service). Uses the server's MCP `name`, so the same
        helper works for both agent classes.
        """

        return self.transport.call(
            sender=self.name,
            receiver=server.name,
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

    # -- Subscription-domain governed actions -----------------------------
    #
    # Each subscription method is structurally identical to the shopping
    # methods above: it constructs a ProposedAction and routes it through
    # the engine. The differences are (a) it attaches the ConsumerContext
    # so the data foundation is provenanced on the resulting record, and
    # (b) it runs the DataContextValidator before reaching PAG so that
    # actions against an incomplete data baseline are refused outright.

    def _attach_context(self, action: ProposedAction) -> ProposedAction:
        if self.context is None:
            return action
        return action.model_copy(update={
            "context_id": self.context.context_id,
            "context_version": self.context.context_version,
        })

    def _emit_context_block(
        self, *, scenario_id: str, action: ProposedAction, reason: str, missing: List[str],
    ) -> DecisionRecord:
        """Build and persist a synthetic BLOCK_MISSING_CONTEXT decision record.

        This is the only place in the agent that records a decision without
        engine.govern() — and only because validation precedes the engine.
        The engine cannot evaluate an action whose data foundation is missing.
        """

        record = DecisionRecord(
            trace_id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            actor=self.name,
            acting_on_behalf_of=self.delegation.acting_on_behalf_of,
            agent_name=self.name,
            action_id=action.action_id,
            intended_action=action.action_type.value,
            action_payload_summary=action.payload_summary(),
            decision=Decision.BLOCK_MISSING_CONTEXT,
            rationale=reason,
            policy_id="data_context_validator",
            policy_version="1.0.0",
            policies_evaluated=["data_context_validator"],
            facts_used={"missing_fields": missing},
            pag_status="not_reached",
            atm_status="aborted",
            paa_status="recorded",
            approval_required=False,
            approval_outcome=None,
            execution_outcome=f"not executed: missing data context ({missing})",
            reversible_flag=action.reversible,
            conditions=[],
            context_id=action.context_id,
            context_version=action.context_version,
        )
        if self.on_context_block is not None:
            self.on_context_block(record)
        return record

    def _govern_subscription_action(
        self,
        *,
        scenario_id: str,
        action: ProposedAction,
        side_effect: Optional[Callable[[ProposedAction], Any]] = None,
        evaluation_extras: Optional[Dict[str, Any]] = None,
        condition_check: Optional[Callable[[ProposedAction], bool]] = None,
    ) -> GovernedOutcome:
        """Run the pre-PAG data validation, then route to engine.govern().

        Returns a GovernedOutcome in both cases. When validation fails a
        synthetic outcome is returned whose DecisionRecord carries the
        BLOCK_MISSING_CONTEXT verdict; the engine is never engaged.
        """

        action = self._attach_context(action)
        if self.context_validator is not None:
            res = self.context_validator.validate(
                action_type=action.action_type, context=self.context
            )
            if not res.passed:
                record = self._emit_context_block(
                    scenario_id=scenario_id, action=action,
                    reason=res.rationale, missing=res.missing,
                )
                return GovernedOutcome(
                    decision=Decision.BLOCK_MISSING_CONTEXT,
                    record=record,
                    pag=PAGOutcome(decision=Decision.BLOCK_MISSING_CONTEXT,
                                    rationale=res.rationale, verdicts=[],
                                    packs_evaluated=[], facts={"missing": res.missing}),
                    atm=None,  # type: ignore[arg-type]  -- aborted before ATM
                    side_effect_result=None,
                )
        return self.engine.govern(
            scenario_id=scenario_id,
            delegation=self.delegation,
            action=action,
            side_effect=side_effect,
            condition_check=condition_check,
            extras={"consumer_context": self.context} if self.context else None,
        )

    def renew_subscription(
        self,
        *,
        scenario_id: str,
        service: SubscriptionServiceAgent,
        monthly_eur: float,
        billing_period: str,
        period_change_accepted: bool = False,
        log_price_drift: bool = False,
    ) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.RENEW_SUBSCRIPTION,
            payload={
                "service": service.service_id,
                "monthly_eur": monthly_eur,
                "billing_period": billing_period,
                "period_change_accepted": period_change_accepted,
                "log_price_drift": log_price_drift,
            },
            reversible=True,
            rationale=f"renewing {service.service_id} at €{monthly_eur:.2f}/mo",
        )
        def _confirm(_a):
            return self._mcp(service, "confirm_renewal", service=service.service_id,
                             shared_fields=["payment_token", "billing_email"])
        return self._govern_subscription_action(
            scenario_id=scenario_id, action=action, side_effect=_confirm,
            condition_check=lambda _a: log_price_drift,
        )

    def cancel_subscription(
        self, *, scenario_id: str, service: SubscriptionServiceAgent,
    ) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.CANCEL_SUBSCRIPTION,
            payload={"service": service.service_id},
            reversible=False,
            rationale=f"cancelling {service.service_id} after governance refusal",
        )
        def _confirm(_a):
            return self._mcp(service, "cancel_subscription", service=service.service_id)
        return self._govern_subscription_action(
            scenario_id=scenario_id, action=action, side_effect=_confirm,
        )

    def accept_terms_change(
        self,
        *,
        scenario_id: str,
        service: SubscriptionServiceAgent,
        new_billing_period: str,
        monthly_eur: float,
        period_change_accepted: bool = False,
    ) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.ACCEPT_TERMS_CHANGE,
            payload={
                "service": service.service_id,
                "billing_period": new_billing_period,
                "monthly_eur": monthly_eur,
                "period_change_accepted": period_change_accepted,
            },
            reversible=True,
            rationale=f"considering terms change on {service.service_id}",
        )
        return self._govern_subscription_action(scenario_id=scenario_id, action=action)

    def share_billing_data(
        self,
        *,
        scenario_id: str,
        service: SubscriptionServiceAgent,
        data_fields_requested: List[str],
    ) -> GovernedOutcome:
        action = ProposedAction(
            action_id=str(uuid.uuid4()),
            delegation_id=self.delegation.delegation_id,
            agent_name=self.name,
            action_type=ActionType.SHARE_BILLING_DATA,
            payload={
                "service": service.service_id,
                "data_fields_requested": list(data_fields_requested),
            },
            reversible=False,
            rationale=f"considering billing-data share with {service.service_id}",
        )
        return self._govern_subscription_action(scenario_id=scenario_id, action=action)
