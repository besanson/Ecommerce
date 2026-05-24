from __future__ import annotations

from gacct.agents.consumer_agent import ConsumerAgent
from gacct.governance.engine import GovernanceEngine
from gacct.scenarios.fixtures import build_consumer_delegation, build_retailers
from gacct.trace.store import TraceStore

SCENARIO_ID = "blocked_path"


def run(engine: GovernanceEngine, store: TraceStore) -> None:
    """Three independent blocks fire:

    1. select_merchant against a denied retailer (Shady Kicks) -> BLOCK
    2. share_consumer_data with Trail Works (asks for phone+marketing) -> BLOCK
    3. accept_return_terms on Shady Kicks's 3-day window -> BLOCK
    """

    delegation = build_consumer_delegation()
    retailers = build_retailers()
    shady = retailers["retailer:shady_kicks"]
    trail = retailers["retailer:trail_works"]
    agent = ConsumerAgent(name="agent:eva-shopper", delegation=delegation, engine=engine)

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="mission_opened",
        actor=agent.name,
        summary="opening shopping mission",
        detail={"mission": delegation.mission},
    )

    agent.select_merchant(scenario_id=SCENARIO_ID, retailer_id=shady.retailer_id)

    agent.share_consumer_data(
        scenario_id=SCENARIO_ID,
        retailer=trail,
        fields=trail.requires_data_fields,
    )

    shady_offer = shady.catalogue[0]
    agent.accept_return_terms(scenario_id=SCENARIO_ID, offer=shady_offer)

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="scenario_completed",
        actor=agent.name,
        summary="blocked path complete; no order placed",
    )
