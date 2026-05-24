from __future__ import annotations

from gacct.agents.consumer_agent import ConsumerAgent
from gacct.governance.engine import GovernanceEngine
from gacct.intent.parser import parse_consumer_intent
from gacct.mcp.transport import MCPTransport
from gacct.reasoning.engine import ConsumerAgentReasoner
from gacct.scenarios.fixtures import DEFAULT_MISSION_TEXT, build_retailers
from gacct.trace.store import TraceStore

SCENARIO_ID = "escalation_path"
MISSION_TEXT = DEFAULT_MISSION_TEXT


def run(engine: GovernanceEngine, store: TraceStore, transport: MCPTransport, seed: int = 42) -> None:
    """Mission begins as happy path. Retailer signals the original SKU is
    actually low on stock and proposes a +14% substitute via MCP. The
    substitution + budget packs both ESCALATE; consumer approves; payment
    on the new total also escalates.
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
    original = next(o for o in offers if o.sku == "RC-AERO-1")

    # The agent explicitly asks the retailer (over MCP) for a substitute.
    substitute = agent._mcp(retailer, "propose_substitute", original_sku=original.sku)
    # In the seeded fixture the chosen substitute is RC-AERO-2 (+14%).

    agent.select_merchant(scenario_id=SCENARIO_ID, retailer_id=retailer.retailer_id)
    agent.accept_substitute(scenario_id=SCENARIO_ID, substitute=substitute, original=original)
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
        actor="agent:eva-shopper",
        summary="escalation path complete",
        detail={"final_offer": substitute.sku, "total_eur": substitute.total_eur},
    )
