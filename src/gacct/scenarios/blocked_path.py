from __future__ import annotations

from gacct.agents.consumer_agent import ConsumerAgent
from gacct.governance.engine import GovernanceEngine
from gacct.intent.parser import parse_consumer_intent
from gacct.mcp.transport import MCPTransport
from gacct.reasoning.engine import ConsumerAgentReasoner
from gacct.scenarios.fixtures import DEFAULT_MISSION_TEXT, build_retailers
from gacct.trace.store import TraceStore

SCENARIO_ID = "blocked_path"
MISSION_TEXT = DEFAULT_MISSION_TEXT


def run(engine: GovernanceEngine, store: TraceStore, transport: MCPTransport, seed: int = 42) -> None:
    """Three independent governance failures:
      1. agent tries a denied retailer -> BLOCK
      2. agent queries Trail Works whose terms exceed the data whitelist -> BLOCK
      3. agent considers Shady Kicks's 3-day return window -> BLOCK
    """

    parsed = parse_consumer_intent(MISSION_TEXT)
    delegation = parsed.delegation

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="mission_opened",
        actor="consumer:eva",
        summary="opening shopping mission",
        detail={
            "mission_text": MISSION_TEXT,
            "parsing_trace": parsed.parsing_trace,
            "delegation": delegation.model_dump(mode="json"),
        },
    )

    retailers = build_retailers(seed=seed)
    shady = retailers["retailer:shady_kicks"]
    trail = retailers["retailer:trail_works"]
    transport.register(shady)
    transport.register(trail)

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

    # 1) Agent considers and tries a denied retailer.
    agent.select_merchant(scenario_id=SCENARIO_ID, retailer_id=shady.retailer_id)

    # 2) Agent asks Trail Works what data it needs, then tries to share - block.
    trail_terms = agent._mcp(trail, "get_terms")
    agent.share_consumer_data(
        scenario_id=SCENARIO_ID,
        retailer=trail,
        fields=trail_terms["requires_data_fields"],
    )

    # 3) Agent inspects Shady Kicks's offer and tries to accept return terms.
    shady_offers = agent._mcp(shady, "list_products", max_results=5)
    shady_offer = shady_offers[0]
    agent.accept_return_terms(scenario_id=SCENARIO_ID, offer=shady_offer)

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="scenario_completed",
        actor="agent:eva-shopper",
        summary="blocked path complete; no order placed",
    )
