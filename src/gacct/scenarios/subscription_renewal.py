"""Subscription renewal — the seven-moment scenario.

Demonstrates the three pillars side-by-side:

  AGENTIC  — the agent walks an end-to-end subscription portfolio, querying
             services, comparing current terms to a versioned baseline, and
             proposing renewals, cancellations, or escalations as needed.
  DATA     — the ConsumerContext is the structured foundation. Stale prices,
             missing fields, and silent term changes are surfaced explicitly.
  GOVERNANCE — every consequential step routes through the engine; a
             DataContextValidator gates incomplete contexts before PAG.

Seven moments:
  1. Netflix renewal (€13.99)                  → ALLOW            [DATA fresh, GOVERNANCE allows]
  2. StreamPlus renewal (9.99 → 10.99, +10%)   → ALLOW_WITH_COND. [DATA drift detected, condition: log_price_drift]
  3. MegaBundle renewal (19 → 34)              → BLOCK            [DATA: stale baseline + GOVERNANCE: over ceiling]
  4. Spotify (new service)                     → ESCALATE         [DATA gap: unknown service]
  5. Aggregator requests full card number      → BLOCK            [DATA: outside whitelist]
  6. AnnualPlus billing-period change          → ESCALATE         [DATA: baseline says monthly]
  7. Action with incomplete context            → BLOCK_MISSING_CONTEXT [DATA: precondition failed]
"""

from __future__ import annotations

from gacct.agents.consumer_agent import ConsumerAgent
from gacct.domain.context import DataContextValidator
from gacct.governance.engine import GovernanceEngine
from gacct.mcp.transport import MCPTransport
from gacct.reasoning.engine import ConsumerAgentReasoner
from gacct.scenarios.fixtures import (
    SUBSCRIPTION_MISSION_TEXT,
    build_subscription_context,
    build_subscription_delegation,
    build_subscription_services,
)
from gacct.trace.store import TraceStore

SCENARIO_ID = "subscription_renewal"
MISSION_TEXT = SUBSCRIPTION_MISSION_TEXT


def run(engine: GovernanceEngine, store: TraceStore, transport: MCPTransport, seed: int = 42) -> None:
    delegation = build_subscription_delegation()
    context = build_subscription_context(with_approved_services_version=True)
    validator = DataContextValidator()

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="mission_opened",
        actor="consumer:eva",
        summary="opening subscription renewal mission",
        detail={
            "mission_text": MISSION_TEXT,
            "delegation": delegation.model_dump(mode="json"),
            "consumer_context": context.model_dump(mode="json"),
            "pillars": {
                "agentic": "agent walks the full subscription portfolio without per-step approval",
                "data":    f"ConsumerContext {context.context_id} v{context.context_version}",
                "governance": "every renewal / share / cancel routed through PAG → ATM → PAA",
            },
        },
    )

    services = build_subscription_services(seed=seed)
    for svc in services.values():
        transport.register(svc)

    reasoner = ConsumerAgentReasoner(delegation, seed=seed)
    agent = ConsumerAgent(
        name="agent:eva-renewer",
        delegation=delegation,
        engine=engine,
        transport=transport,
        reasoner=reasoner,
        on_thought=lambda t: store.record_thought(
            scenario_id=SCENARIO_ID, actor="agent:eva-renewer", topic=t.topic, content=t.content,
        ),
        context=context,
        context_validator=validator,
        on_context_block=store.record_decision,
    )

    # 1. Netflix — fresh data, under threshold → ALLOW
    netflix = services["netflix"]
    netflix_terms = agent._mcp(netflix, "get_renewal_terms")
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=netflix,
        monthly_eur=netflix_terms["monthly_eur"],
        billing_period=netflix_terms["billing_period"],
    )

    # 2. StreamPlus — +10% drift within tolerance → ALLOW_WITH_CONDITIONS
    streamplus = services["streamplus"]
    sp_terms = agent._mcp(streamplus, "get_renewal_terms")
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=streamplus,
        monthly_eur=sp_terms["monthly_eur"],
        billing_period=sp_terms["billing_period"],
        log_price_drift=True,
    )
    # The agent now updates its baseline forward so future steps see the new price.
    agent.context = agent.context.bumped(subscriptions={
        **agent.context.data_baseline["subscriptions"],
        "streamplus": {"monthly_eur": sp_terms["monthly_eur"], "billing_period": "monthly", "fresh": True},
    })

    # 3. MegaBundle — jumped past block ceiling → BLOCK
    megabundle = services["megabundle"]
    mb_terms = agent._mcp(megabundle, "get_renewal_terms")
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=megabundle,
        monthly_eur=mb_terms["monthly_eur"],
        billing_period=mb_terms["billing_period"],
    )

    # 4. Spotify — unknown service → ESCALATE (data gap)
    spotify = services["spotify"]
    spot_terms = agent._mcp(spotify, "get_renewal_terms")
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=spotify,
        monthly_eur=spot_terms["monthly_eur"],
        billing_period=spot_terms["billing_period"],
    )

    # 5. Aggregator requests full card number → BLOCK (data sharing whitelist)
    aggregator = services["aggregator"]
    agg_terms = agent._mcp(aggregator, "get_renewal_terms")
    agent.share_billing_data(
        scenario_id=SCENARIO_ID, service=aggregator,
        data_fields_requested=agg_terms["requires_data_fields"],
    )

    # 6. AnnualPlus — silently switched to annual billing → ESCALATE (data: baseline says monthly)
    annualplus = services["annualplus"]
    ap_terms = agent._mcp(annualplus, "get_renewal_terms")
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=annualplus,
        monthly_eur=ap_terms["monthly_eur"],
        billing_period=ap_terms["billing_period"],
    )

    # 7. Incomplete context — clear the approved_services_version field
    # and try to renew → BLOCK_MISSING_CONTEXT before PAG is reached.
    stale_context = build_subscription_context(with_approved_services_version=False)
    agent.context = stale_context
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=netflix,
        monthly_eur=netflix.monthly_eur,
        billing_period=netflix.billing_period,
    )

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="scenario_completed",
        actor="agent:eva-renewer",
        summary="subscription renewal mission complete",
        detail={"context_version_at_end": agent.context.context_version},
    )
