from __future__ import annotations

from gacct.agents.consumer_agent import ConsumerAgent
from gacct.governance.engine import GovernanceEngine
from gacct.intent.parser import parse_consumer_intent
from gacct.mcp.transport import MCPTransport
from gacct.reasoning.engine import ConsumerAgentReasoner
from gacct.scenarios.fixtures import DEFAULT_MISSION_TEXT, build_retailers
from gacct.trace.store import TraceStore

SCENARIO_ID = "conditional_path"
MISSION_TEXT = DEFAULT_MISSION_TEXT


def run(engine: GovernanceEngine, store: TraceStore, transport: MCPTransport, seed: int = 42) -> None:
    parsed = parse_consumer_intent(MISSION_TEXT)
    delegation = parsed.delegation

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="mission_opened",
        actor="consumer:eva",
        summary="opening shopping mission with loyalty promo on offer",
        detail={
            "mission_text": MISSION_TEXT,
            "parsing_trace": parsed.parsing_trace,
            "delegation": delegation.model_dump(mode="json"),
        },
    )

    retailers = build_retailers(seed=seed)
    retailer = retailers["retailer:run_co"]
    transport.register(retailer)

    reasoner = ConsumerAgentReasoner(delegation, seed=seed)
    agent = ConsumerAgent(
        name="agent:eva-shopper",
        delegation=delegation,
        engine=engine,
        transport=transport,
        reasoner=reasoner,
        on_thought=lambda t: store.record_thought(
            scenario_id=SCENARIO_ID, actor="agent:eva-shopper", topic=t.topic, content=t.content
        ),
    )

    offers = agent.discover_offers(retailer)
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
        actor="agent:eva-shopper",
        summary="conditional path complete; promotion applied with explicit consumer condition",
    )
