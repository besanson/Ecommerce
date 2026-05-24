from __future__ import annotations

from gacct.agents.consumer_agent import ConsumerAgent
from gacct.governance.engine import GovernanceEngine
from gacct.scenarios.fixtures import build_consumer_delegation, build_retailers
from gacct.trace.store import TraceStore

SCENARIO_ID = "escalation_path"


def run(engine: GovernanceEngine, store: TraceStore) -> None:
    """Substitute outside tolerance escalates; once approved, order proceeds
    but the auto-buy threshold then forces a second escalation for payment.
    """

    delegation = build_consumer_delegation()
    retailers = build_retailers()
    retailer = retailers["retailer:run_co"]
    agent = ConsumerAgent(name="agent:eva-shopper", delegation=delegation, engine=engine)

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="mission_opened",
        actor=agent.name,
        summary="opening shopping mission",
        detail={"mission": delegation.mission},
    )

    catalogue = retailer.search()
    original = next(o for o in catalogue if o.sku == "RC-AERO-1")
    substitute = next(o for o in catalogue if o.sku == "RC-AERO-2")
    substitute = substitute.model_copy(update={"substitute_for_offer_id": original.offer_id})

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="offer_received",
        actor=retailer.retailer_id,
        summary=(
            f"original {original.sku} {original.price_eur:.2f} EUR; "
            f"substitute {substitute.sku} {substitute.price_eur:.2f} EUR"
        ),
        detail={"original_sku": original.sku, "substitute_sku": substitute.sku},
    )

    agent.select_merchant(scenario_id=SCENARIO_ID, retailer_id=retailer.retailer_id)

    # Substitute is +14.4% — outside the 10% tolerance -> ESCALATE.
    agent.accept_substitute(scenario_id=SCENARIO_ID, substitute=substitute, original=original)

    # Even though the substitute is approved, total 159 + 6 = 165 EUR > 150 EUR auto-buy → ESCALATE again.
    agent.accept_return_terms(scenario_id=SCENARIO_ID, offer=substitute)
    agent.share_consumer_data(
        scenario_id=SCENARIO_ID,
        retailer=retailer,
        fields=["shipping_address", "payment_token_id"],
    )
    agent.place_order(
        scenario_id=SCENARIO_ID,
        retailer=retailer,
        offer=substitute,
        shared_fields=["shipping_address", "payment_token_id"],
    )
    agent.use_payment_token(
        scenario_id=SCENARIO_ID,
        amount_eur=substitute.total_eur,
        retailer_id=retailer.retailer_id,
    )

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="scenario_completed",
        actor=agent.name,
        summary="escalation path complete",
        detail={"final_offer": substitute.sku, "total_eur": substitute.total_eur},
    )
