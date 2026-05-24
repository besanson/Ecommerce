"""Executive control room for delegated commerce.

Loads pre-generated scenario traces, lets the operator switch scenarios, and
surfaces five views: mission, agent network, decision ledger, KPI cockpit,
and per-decision forensics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gacct.domain.decisions import DecisionRecord
from gacct.scenarios.fixtures import build_consumer_delegation
from gacct.scenarios.runner import SCENARIO_BUILDERS, run_scenario
from gacct.trace.store import TraceStore

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples" / "traces"
RUNTIME_DIR = REPO_ROOT / "traces" / "runtime"

DECISION_COLORS = {
    "allow": "#1f9e4a",
    "allow_with_conditions": "#1f6fb0",
    "escalate": "#d18a00",
    "block": "#c62828",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_traces(trace_dir: Path) -> Dict[str, List[dict]]:
    if not trace_dir.exists():
        return {}
    store = TraceStore.load(trace_dir)
    out: Dict[str, List[dict]] = {}
    for sid in store.all_scenarios():
        out[sid] = [e.model_dump(mode="json") for e in store.events_for(sid)]
    return out


def _decision_records(events: List[dict]) -> List[DecisionRecord]:
    return [DecisionRecord.model_validate(e["detail"]) for e in events if e["event_type"] == "decision"]


# ---------------------------------------------------------------------------
# UI components
# ---------------------------------------------------------------------------


def render_mission_view(events: List[dict]) -> None:
    delegation = build_consumer_delegation()
    st.subheader("Mission")
    st.markdown(f"**{delegation.mission}** — acting on behalf of `{delegation.consumer_id}`")

    cols = st.columns(3)
    cols[0].metric("Budget ceiling", f"€{delegation.budget_ceiling_eur:,.0f}")
    cols[1].metric("Auto-buy threshold", f"€{delegation.auto_buy_threshold_eur:,.0f}")
    cols[2].metric("Delivery deadline", f"{delegation.delivery_deadline_days} days")

    cols = st.columns(3)
    cols[0].metric("Substitution tolerance", f"{delegation.substitution_tolerance_pct:.0%}")
    cols[1].metric("Min return window", f"{delegation.min_return_window_days} days")
    cols[2].metric("Forbidden materials", ", ".join(delegation.forbidden_materials) or "—")

    with st.expander("Delegated authority detail", expanded=False):
        st.markdown("**Approved retailers**: " + ", ".join(f"`{r}`" for r in delegation.approved_retailers))
        st.markdown("**Denied retailers**: " + (", ".join(f"`{r}`" for r in delegation.denied_retailers) or "—"))
        st.markdown("**Permitted data fields**: " + ", ".join(f"`{f}`" for f in delegation.permitted_data_fields))
        st.markdown(f"**Notes**: {delegation.notes or '—'}")

    records = _decision_records(events)
    if not records:
        return
    last = records[-1]
    status = "in progress" if last.execution_outcome.startswith("executed") else last.execution_outcome
    st.caption(f"Mission status: last action `{last.intended_action}` → **{last.decision.value.upper()}** ({status})")


def render_agent_network() -> None:
    st.subheader("Agent network")
    g = nx.DiGraph()
    nodes = [
        ("consumer", {"label": "Consumer (human)", "tier": 0}),
        ("consumer_agent", {"label": "Consumer agent", "tier": 1}),
        ("governance", {"label": "Governance layer\n(PAG / ATM / PAA)", "tier": 2}),
        ("approval", {"label": "Approval service", "tier": 2}),
        ("payment_boundary", {"label": "Payment token\nauthority boundary", "tier": 2}),
        ("retailer_agent", {"label": "Retailer agent", "tier": 3}),
        ("trace_store", {"label": "Trace store", "tier": 3}),
    ]
    for n, attrs in nodes:
        g.add_node(n, **attrs)
    edges = [
        ("consumer", "consumer_agent", "delegates mission"),
        ("consumer_agent", "governance", "proposes action"),
        ("governance", "approval", "escalates"),
        ("approval", "governance", "approves / rejects"),
        ("governance", "payment_boundary", "authorizes / denies"),
        ("governance", "retailer_agent", "executes side effect"),
        ("retailer_agent", "consumer_agent", "returns offers"),
        ("governance", "trace_store", "writes decision record"),
    ]
    for s, t, label in edges:
        g.add_edge(s, t, label=label)

    pos = {
        "consumer": (0, 2),
        "consumer_agent": (1, 2),
        "governance": (2, 2),
        "approval": (2, 3.2),
        "payment_boundary": (3, 1),
        "retailer_agent": (3, 2),
        "trace_store": (3, 3),
    }

    edge_x, edge_y, edge_text = [], [], []
    for s, t, d in g.edges(data=True):
        x0, y0 = pos[s]
        x1, y1 = pos[t]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        edge_text.append(f"{s} → {t}: {d['label']}")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=edge_x, y=edge_y, mode="lines",
            line=dict(width=1.2, color="#888"), hoverinfo="none",
        )
    )
    node_x = [pos[n][0] for n in g.nodes]
    node_y = [pos[n][1] for n in g.nodes]
    labels = [g.nodes[n]["label"] for n in g.nodes]
    colors = ["#c62828" if n == "governance" else "#1f6fb0" if "agent" in n else "#555" for n in g.nodes]
    fig.add_trace(
        go.Scatter(
            x=node_x, y=node_y, mode="markers+text",
            marker=dict(size=44, color=colors, line=dict(width=1.5, color="white")),
            text=labels, textposition="middle center",
            textfont=dict(size=10, color="white"),
            hovertext=edge_text, hoverinfo="text",
        )
    )
    fig.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        height=380,
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Governance sits between intent and consequence. Every consequential "
        "action flows through PAG / ATM / PAA. Retailer-side side effects only "
        "fire if ATM authorizes execution."
    )


def render_ledger(events: List[dict]) -> None:
    st.subheader("Decision ledger")
    records = _decision_records(events)
    if not records:
        st.info("No governed actions in this scenario yet.")
        return
    rows = []
    for r in records:
        rows.append({
            "timestamp": r.timestamp.isoformat(timespec="seconds"),
            "actor": r.actor,
            "on_behalf_of": r.acting_on_behalf_of,
            "intended_action": r.intended_action,
            "decision": r.decision.value,
            "policy": r.policy_id or "—",
            "rationale": r.rationale,
            "approval_required": r.approval_required,
            "outcome": r.execution_outcome,
        })
    df = pd.DataFrame(rows)

    def _row_style(row):
        color = DECISION_COLORS.get(row["decision"], "#444")
        return [f"background-color: {color}22"] * len(row)

    st.dataframe(df.style.apply(_row_style, axis=1), use_container_width=True, hide_index=True)


def render_cockpit(events: List[dict]) -> None:
    st.subheader("Commerce cockpit")
    records = _decision_records(events)
    delegation = build_consumer_delegation()
    attempted = len(records)
    allowed = sum(1 for r in records if r.decision.value in ("allow", "allow_with_conditions"))
    blocked = sum(1 for r in records if r.decision.value == "block")
    escalated = sum(1 for r in records if r.decision.value == "escalate")

    budget_consumed = 0.0
    discount_captured = 0.0
    for r in records:
        if r.execution_outcome.startswith("executed") and r.intended_action == "place_order":
            facts = r.facts_used.get("budget.over_ceiling", {})
            budget_consumed += float(facts.get("total_eur", 0.0))
        if r.execution_outcome.startswith("executed") and r.intended_action == "apply_promotion":
            facts = r.facts_used.get("promotions.must_reduce_total", {})
            discount_captured += float(facts.get("discount_eur", 0.0))

    cols = st.columns(4)
    cols[0].metric("Actions attempted", attempted)
    cols[1].metric("Allowed", allowed)
    cols[2].metric("Blocked", blocked)
    cols[3].metric("Escalations", escalated)

    cols = st.columns(2)
    cols[0].metric(
        "Budget consumed",
        f"€{budget_consumed:,.2f}",
        f"of €{delegation.budget_ceiling_eur:,.0f} ceiling",
    )
    cols[1].metric("Discounts captured", f"€{discount_captured:,.2f}")


def render_forensics(events: List[dict]) -> None:
    st.subheader("Forensics / dispute view")
    records = _decision_records(events)
    if not records:
        st.info("Nothing to inspect.")
        return
    options = {
        f"#{i+1}  {r.intended_action} → {r.decision.value}": i
        for i, r in enumerate(records)
    }
    label = st.selectbox("Pick a decision to inspect", list(options.keys()))
    r = records[options[label]]

    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Delegated authority**")
        d = build_consumer_delegation()
        st.json({
            "consumer_id": d.consumer_id,
            "budget_ceiling_eur": d.budget_ceiling_eur,
            "auto_buy_threshold_eur": d.auto_buy_threshold_eur,
            "approved_retailers": d.approved_retailers,
            "denied_retailers": d.denied_retailers,
            "forbidden_materials": d.forbidden_materials,
            "substitution_tolerance_pct": d.substitution_tolerance_pct,
            "permitted_data_fields": d.permitted_data_fields,
            "min_return_window_days": d.min_return_window_days,
        }, expanded=False)
    with cols[1]:
        st.markdown("**Proposed action**")
        st.json({
            "action_id": r.action_id,
            "intended_action": r.intended_action,
            "payload_summary": r.action_payload_summary,
            "actor": r.actor,
            "reversible": r.reversible_flag,
        }, expanded=False)

    st.markdown("**Pipeline outcome**")
    pipe = pd.DataFrame([
        {"stage": "PAG (Pre-Action Gate)", "status": r.pag_status},
        {"stage": "ATM (Action-Time Monitor)", "status": r.atm_status},
        {"stage": "PAA (Post-Action Audit)", "status": r.paa_status},
    ])
    st.table(pipe)

    cols = st.columns(2)
    cols[0].markdown("**Policies evaluated**")
    cols[0].write(r.policies_evaluated or "—")
    cols[1].markdown("**Approval**")
    cols[1].write({
        "required": r.approval_required,
        "outcome": r.approval_outcome or "—",
    })

    st.markdown("**Facts used**")
    st.json(r.facts_used or {}, expanded=False)

    st.markdown("**Rationale**")
    st.info(r.rationale)

    st.markdown("**Final result**")
    st.code(r.execution_outcome)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="Governed Agentic Commerce Control Tower",
        layout="wide",
    )
    st.title("Governed Agentic Commerce Control Tower")
    st.caption(
        "Runtime governance for delegated commerce. Governance is enforced at "
        "explicitly wrapped action boundaries only. Simulated environment; not "
        "a production-certified commerce system."
    )

    with st.sidebar:
        st.header("Scenario")
        source = st.radio(
            "Trace source",
            options=["Pre-generated examples", "Run fresh"],
            index=0,
        )
        trace_dir = EXAMPLES_DIR if source == "Pre-generated examples" else RUNTIME_DIR
        scenarios = list(SCENARIO_BUILDERS.keys())
        scenario = st.selectbox("Scenario", scenarios)
        if source == "Run fresh":
            if st.button("Re-run scenario"):
                RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
                # Reset file so a re-run is deterministic.
                target = RUNTIME_DIR / f"{scenario}.jsonl"
                if target.exists():
                    target.unlink()
                run_scenario(scenario, out_dir=RUNTIME_DIR)
                st.success(f"ran {scenario}")
        st.divider()
        st.caption(
            "Built-in scenarios:\n"
            "- happy_path — every action ALLOW\n"
            "- escalation_path — substitute + auto-buy trigger ESCALATE\n"
            "- blocked_path — denied retailer, excess data sharing, weak returns\n"
            "- conditional_path — loyalty promo as ALLOW_WITH_CONDITIONS"
        )

    traces = _load_traces(trace_dir)
    events = traces.get(scenario, [])
    if not events:
        st.warning(
            f"No trace found for `{scenario}` under `{trace_dir.relative_to(REPO_ROOT)}`. "
            "Run `make scenarios` or use the 'Run fresh' option."
        )
        return

    tabs = st.tabs(["Mission", "Agent network", "Ledger", "Cockpit", "Forensics"])
    with tabs[0]:
        render_mission_view(events)
    with tabs[1]:
        render_agent_network()
    with tabs[2]:
        render_ledger(events)
    with tabs[3]:
        render_cockpit(events)
    with tabs[4]:
        render_forensics(events)


if __name__ == "__main__":
    main()
