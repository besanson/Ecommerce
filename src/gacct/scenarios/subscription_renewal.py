"""Subscription renewal - the seven-moment headline scenario.

Eva delegates her entire subscription portfolio to the agent. The agent walks
the portfolio end-to-end (AGENTIC), comparing each service's current terms
against a versioned ConsumerContext (DATA), and routing every consequential
step through PAG -> ATM -> PAA (GOVERNANCE).

Seven moments, one per real-world service:

  1. Netflix (€13.99)              -> ALLOW                  [under €15 auto-renew threshold]
  2. Spotify Premium (€10.49,+5%)  -> ALLOW_WITH_CONDITIONS  [drift within tolerance, condition: log_price_drift]
  3. DAZN Total (€34.99)           -> BLOCK                  [over €30 block ceiling + stale baseline]
  4. Apple TV+ (new service)       -> ESCALATE               [data gap: not on approved list]
  5. BundleSavvy aggregator        -> BLOCK                  [data sharing: full card # outside whitelist]
  6. Amazon Prime monthly->annual  -> ESCALATE               [data: baseline says monthly, service silently switched]
  7. Disney+ with stale context    -> BLOCK_MISSING_CONTEXT  [data foundation is a governance precondition]
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
                "governance": "every renewal / share / cancel routed through PAG -> ATM -> PAA",
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

    # 1. Netflix - fresh data, under threshold -> ALLOW
    netflix = services["netflix"]
    netflix_terms = agent._mcp(netflix, "get_renewal_terms")
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=netflix,
        monthly_eur=netflix_terms["monthly_eur"],
        billing_period=netflix_terms["billing_period"],
    )

    # 2. Spotify Premium - +10% drift within tolerance -> ALLOW_WITH_CONDITIONS
    spotify = services["spotify"]
    sp_terms = agent._mcp(spotify, "get_renewal_terms")
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=spotify,
        monthly_eur=sp_terms["monthly_eur"],
        billing_period=sp_terms["billing_period"],
        log_price_drift=True,
    )
    # Agent updates its baseline so future steps see the new Spotify price.
    agent.context = agent.context.bumped(subscriptions={
        **agent.context.data_baseline["subscriptions"],
        "spotify": {"monthly_eur": sp_terms["monthly_eur"], "billing_period": "monthly", "fresh": True},
    })

    # 3. DAZN Total - jumped past block ceiling -> BLOCK
    dazn = services["dazn"]
    dazn_terms = agent._mcp(dazn, "get_renewal_terms")
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=dazn,
        monthly_eur=dazn_terms["monthly_eur"],
        billing_period=dazn_terms["billing_period"],
    )

    # 4. Apple TV+ - unknown service, not on approved list -> ESCALATE
    apple_tv = services["apple_tv"]
    apple_terms = agent._mcp(apple_tv, "get_renewal_terms")
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=apple_tv,
        monthly_eur=apple_terms["monthly_eur"],
        billing_period=apple_terms["billing_period"],
    )

    # 5. BundleSavvy aggregator requests full card number -> BLOCK
    aggregator = services["bundle_savvy"]
    agg_terms = agent._mcp(aggregator, "get_renewal_terms")
    agent.share_billing_data(
        scenario_id=SCENARIO_ID, service=aggregator,
        data_fields_requested=agg_terms["requires_data_fields"],
    )

    # 6. Amazon Prime - silently switched from monthly to annual -> ESCALATE
    prime = services["amazon_prime"]
    prime_terms = agent._mcp(prime, "get_renewal_terms")
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=prime,
        monthly_eur=prime_terms["monthly_eur"],
        billing_period=prime_terms["billing_period"],
    )

    # 7. Disney+ renewal against an incomplete context
    # (missing approved_services_version) -> BLOCK_MISSING_CONTEXT
    stale_context = build_subscription_context(with_approved_services_version=False)
    agent.context = stale_context
    disney = services["disney_plus"]
    agent.renew_subscription(
        scenario_id=SCENARIO_ID, service=disney,
        monthly_eur=disney.monthly_eur,
        billing_period=disney.billing_period,
    )

    store.record_event(
        scenario_id=SCENARIO_ID,
        event_type="scenario_completed",
        actor="agent:eva-renewer",
        summary="subscription renewal mission complete",
        detail={"context_version_at_end": agent.context.context_version},
    )
