from __future__ import annotations

from gacct.agents.consumer_agent import ConsumerAgent
from gacct.governance.engine import GovernanceEngine
from gacct.scenarios.fixtures import build_consumer_delegation, build_retailers
from gacct.trace.store import TraceStore

SCENARIO_ID = "happy_path"


def run(engine: GovernanceEngine, store: TraceStore) -> None:
    delegation = build_consumer_delegation()
    retailers = build_retailers()
    retailer = retailers["retailer:run_co"]
    agent = ConsumerAgent(name="agent:eva-shopper", delegation=delegation, engine=engine)

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="mission_opened",
        actor=agent.name,
        summary="opening shopping mission",
        detail={"mission": delegation.mission, "budget_ceiling_eur": delegation.budget_ceiling_eur},
    )

    offers = retailer.search()
    shortlist = agent.shortlist(offers)
    target = shortlist[0]

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="offer_received",
        actor=retailer.retailer_id,
        summary=f"retailer returned {len(offers)} offers; agent shortlisted {target.sku}",
        detail={"shortlist": [o.sku for o in shortlist]},
    )

    agent.select_merchant(scenario_id=SCENARIO_ID, retailer_id=retailer.retailer_id)
    agent.accept_return_terms(scenario_id=SCENARIO_ID, offer=target)
    agent.share_consumer_data(
        scenario_id=SCENARIO_ID,
        retailer=retailer,
        fields=["shipping_address", "payment_token_id"],
    )
    agent.place_order(
        scenario_id=SCENARIO_ID,
        retailer=retailer,
        offer=target,
        shared_fields=["shipping_address", "payment_token_id"],
    )
    agent.use_payment_token(
        scenario_id=SCENARIO_ID,
        amount_eur=target.total_eur,
        retailer_id=retailer.retailer_id,
    )

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="scenario_completed",
        actor=agent.name,
        summary="happy path complete",
        detail={"final_offer": target.sku, "total_eur": target.total_eur},
    )
