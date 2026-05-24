from __future__ import annotations

from gacct.agents.consumer_agent import ConsumerAgent
from gacct.governance.engine import GovernanceEngine
from gacct.scenarios.fixtures import build_consumer_delegation, build_retailers
from gacct.trace.store import TraceStore

SCENARIO_ID = "conditional_path"


def run(engine: GovernanceEngine, store: TraceStore) -> None:
    """A loyalty promotion is offered. It reduces the total but requires a
    marketing_consent field. The promotions pack returns ALLOW_WITH_CONDITIONS;
    the consumer agent passes a condition_check that the consumer has flipped
    the explicit `loyalty_enrollment_accepted` flag.
    """

    delegation = build_consumer_delegation()
    retailers = build_retailers()
    retailer = retailers["retailer:run_co"]
    agent = ConsumerAgent(name="agent:eva-shopper", delegation=delegation, engine=engine)

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="mission_opened",
        actor=agent.name,
        summary="opening shopping mission with loyalty promo on offer",
    )

    offers = retailer.search()
    target = next(o for o in offers if o.sku == "RC-AERO-1")

    agent.select_merchant(scenario_id=SCENARIO_ID, retailer_id=retailer.retailer_id)
    agent.accept_return_terms(scenario_id=SCENARIO_ID, offer=target)

    consumer_opted_in = True

    agent.apply_promotion(
        scenario_id=SCENARIO_ID,
        offer=target,
        discount_eur=15.0,
        requires_data_fields=["marketing_consent"],
        condition_check=lambda _a: consumer_opted_in,
    )

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
        summary="conditional path complete; promotion applied with explicit consumer condition",
    )
