"""Control room for delegated commerce — step-through, narrative-led.

The previous version dropped tables on the user. This version walks one
governed action at a time: shows the consumer's intent, what the governance
layer decided, what actually happened, and which path through the system the
action took. The network diagram lights up the live path for the selected
step. A prev/play/next stepper drives the whole view.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Make the in-repo `gacct` package importable without needing `pip install .`,
# so Streamlit Cloud (which caches `pip install .` results) always sees the
# current sources on every pull.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typing import Dict, List, Optional, Tuple  # noqa: E402

import networkx as nx  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from gacct.domain.decisions import DecisionRecord  # noqa: E402
from gacct.scenarios.fixtures import build_consumer_delegation  # noqa: E402
from gacct.scenarios.narrative import SCENARIO_BRIEFS, brief, step_label  # noqa: E402
from gacct.scenarios.runner import SCENARIO_BUILDERS, run_scenario  # noqa: E402
from gacct.trace.store import TraceStore  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples" / "traces"
RUNTIME_DIR = REPO_ROOT / "traces" / "runtime"

DECISION_COLORS = {
    "allow": "#2e7d32",
    "allow_with_conditions": "#1565c0",
    "escalate": "#ef6c00",
    "block": "#c62828",
}
DECISION_LABELS = {
    "allow": "ALLOW",
    "allow_with_conditions": "ALLOW · WITH CONDITIONS",
    "escalate": "ESCALATE",
    "block": "BLOCK",
}
EVENT_KIND_COLORS = {
    "mission_opened": "#37474f",
    "offer_received": "#37474f",
    "scenario_completed": "#37474f",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_traces(trace_dir: Path) -> Dict[str, List[dict]]:
    if not trace_dir.exists():
        return {}
    store = TraceStore.load(trace_dir)
    return {sid: [e.model_dump(mode="json") for e in store.events_for(sid)] for sid in store.all_scenarios()}


def _decision_records(events: List[dict]) -> List[DecisionRecord]:
    return [DecisionRecord.model_validate(e["detail"]) for e in events if e["event_type"] == "decision"]


# ---------------------------------------------------------------------------
# CSS / theming
# ---------------------------------------------------------------------------


CUSTOM_CSS = """
<style>
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1400px; }
.card {
    border: 1px solid #e0e3e7;
    border-radius: 10px;
    padding: 14px 16px;
    background: #ffffff;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    height: 100%;
}
.card h4 {
    margin: 0 0 8px 0;
    font-size: 0.78rem;
    color: #607d8b;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 600;
}
.decision-badge {
    display: inline-block;
    padding: 6px 14px;
    border-radius: 999px;
    color: white;
    font-weight: 700;
    font-size: 0.95rem;
    letter-spacing: 0.04em;
}
.pipe { display: flex; gap: 8px; align-items: center; margin: 10px 0 4px; }
.pipe-cell {
    flex: 1;
    text-align: center;
    padding: 6px 8px;
    border-radius: 6px;
    background: #eceff1;
    font-size: 0.75rem;
    font-weight: 600;
    color: #455a64;
}
.pipe-cell.on   { background: #2e7d32; color: white; }
.pipe-cell.warn { background: #ef6c00; color: white; }
.pipe-cell.bad  { background: #c62828; color: white; }
.pipe-cell.cond { background: #1565c0; color: white; }
.pipe-arrow { color: #b0bec5; font-weight: bold; }
.muted { color: #607d8b; font-size: 0.85rem; }
.kv { font-size: 0.85rem; line-height: 1.4; }
.kv b { color: #37474f; }
.scenario-brief {
    background: #f5f7fa;
    border-left: 3px solid #455a64;
    padding: 10px 14px;
    border-radius: 4px;
    font-size: 0.92rem;
    margin-bottom: 0.8rem;
}
.step-line {
    background: #fffde7;
    border-left: 3px solid #fbc02d;
    padding: 8px 12px;
    border-radius: 4px;
    font-size: 0.95rem;
    margin-top: 0.4rem;
}
</style>
"""


# ---------------------------------------------------------------------------
# Network diagram — highlights the live path for the selected step
# ---------------------------------------------------------------------------


NODE_POSITIONS = {
    "consumer": (0.05, 0.5),
    "consumer_agent": (0.25, 0.5),
    "governance": (0.50, 0.5),
    "approval": (0.50, 0.88),
    "trace_store": (0.50, 0.12),
    "retailer_agent": (0.78, 0.7),
    "payment_boundary": (0.78, 0.3),
}
NODE_LABELS = {
    "consumer": "Consumer",
    "consumer_agent": "Consumer Agent",
    "governance": "Governance\n(PAG · ATM · PAA)",
    "approval": "Approval Service",
    "trace_store": "Trace Store",
    "retailer_agent": "Retailer Agent",
    "payment_boundary": "Payment Token\nBoundary",
}
EDGES = [
    ("consumer", "consumer_agent"),
    ("consumer_agent", "governance"),
    ("governance", "approval"),
    ("approval", "governance"),
    ("governance", "retailer_agent"),
    ("governance", "payment_boundary"),
    ("governance", "trace_store"),
    ("retailer_agent", "consumer_agent"),
]


def _active_edges(decision: str, action_type: str, approval_outcome: Optional[str]) -> List[Tuple[str, str]]:
    """Pick which edges to highlight for a given decision."""

    base = [("consumer", "consumer_agent"), ("consumer_agent", "governance")]
    trace = [("governance", "trace_store")]
    target = "retailer_agent"
    if action_type == "use_payment_token":
        target = "payment_boundary"
    elif action_type == "select_merchant":
        target = "retailer_agent"

    if decision == "allow" or decision == "allow_with_conditions":
        return base + [("governance", target)] + trace
    if decision == "block":
        return base + trace
    if decision == "escalate":
        path = base + [("governance", "approval"), ("approval", "governance")]
        if approval_outcome == "approved":
            path += [("governance", target)]
        return path + trace
    return base + trace


def render_network(event: Optional[dict], color: str) -> None:
    g = nx.DiGraph()
    for n in NODE_POSITIONS:
        g.add_node(n)
    for e in EDGES:
        g.add_edge(*e)

    active = set()
    if event and event.get("event_type") == "decision":
        d = event["detail"]
        active = set(_active_edges(d["decision"], d["intended_action"], d.get("approval_outcome")))

    edge_traces = []
    for s, t in EDGES:
        x0, y0 = NODE_POSITIONS[s]
        x1, y1 = NODE_POSITIONS[t]
        is_active = (s, t) in active
        edge_traces.append(
            go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode="lines",
                line=dict(
                    width=4 if is_active else 1.3,
                    color=color if is_active else "#cfd8dc",
                ),
                hoverinfo="none",
                showlegend=False,
            )
        )

    # Arrowheads for active edges via annotations
    annotations = []
    for s, t in EDGES:
        if (s, t) not in active:
            continue
        x0, y0 = NODE_POSITIONS[s]
        x1, y1 = NODE_POSITIONS[t]
        annotations.append(
            dict(
                ax=x0, ay=y0, x=x1, y=y1, xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=3, arrowsize=1.6, arrowwidth=2, arrowcolor=color,
            )
        )

    node_x, node_y, node_text, node_color, node_border = [], [], [], [], []
    for n, (x, y) in NODE_POSITIONS.items():
        node_x.append(x)
        node_y.append(y)
        node_text.append(NODE_LABELS[n])
        if n == "governance":
            node_color.append(color if event and event.get("event_type") == "decision" else "#455a64")
            node_border.append("#263238")
        elif n == "approval" and event and event.get("event_type") == "decision" and event["detail"]["decision"] == "escalate":
            node_color.append("#ef6c00")
            node_border.append("#263238")
        elif n == "trace_store":
            node_color.append("#607d8b")
            node_border.append("#37474f")
        elif "agent" in n:
            node_color.append("#1565c0")
            node_border.append("#0d47a1")
        else:
            node_color.append("#90a4ae")
            node_border.append("#546e7a")

    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        marker=dict(size=58, color=node_color, line=dict(width=2, color=node_border)),
        text=node_text,
        textposition="middle center",
        textfont=dict(size=10, color="white", family="Arial Black"),
        hoverinfo="text",
        showlegend=False,
    )

    fig = go.Figure(data=edge_traces + [node_trace])
    fig.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        height=320,
        xaxis=dict(range=[-0.05, 1.0], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[0, 1.02], showgrid=False, zeroline=False, visible=False),
        plot_bgcolor="#fafbfc",
        paper_bgcolor="#fafbfc",
        annotations=annotations,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


def render_intent_card(event: dict) -> None:
    if event["event_type"] != "decision":
        st.markdown(
            f"""
            <div class="card">
              <h4>Context event</h4>
              <div class="kv"><b>{event['event_type'].replace('_', ' ').title()}</b></div>
              <div class="kv muted">{event['summary']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    d = event["detail"]
    payload_summary = d["action_payload_summary"]
    st.markdown(
        f"""
        <div class="card">
          <h4>Consumer agent intent</h4>
          <div class="kv"><b>Action</b>: {d['intended_action'].replace('_', ' ')}</div>
          <div class="kv"><b>Actor</b>: <code>{d['actor']}</code></div>
          <div class="kv"><b>Acting on behalf of</b>: <code>{d['acting_on_behalf_of']}</code></div>
          <div class="kv"><b>Reversible</b>: {'no' if not d['reversible_flag'] else 'yes'}</div>
          <div class="kv muted" style="margin-top:8px;"><b>Payload</b>: <code>{payload_summary}</code></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_governance_card(event: dict) -> None:
    if event["event_type"] != "decision":
        st.markdown(
            """
            <div class="card">
              <h4>Governance</h4>
              <div class="kv muted">Context event — no governance verdict.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    d = event["detail"]
    decision = d["decision"]
    color = DECISION_COLORS[decision]
    label = DECISION_LABELS[decision]

    pag_cls = {"allow": "on", "block": "bad", "escalate": "warn", "allow_with_conditions": "cond"}[decision]
    atm_cls = "on" if d["atm_status"] == "executed" else "bad"
    paa_cls = "on"

    pipe_html = (
        f'<div class="pipe">'
        f'<div class="pipe-cell {pag_cls}">PAG · {d["pag_status"]}</div>'
        f'<div class="pipe-arrow">→</div>'
        f'<div class="pipe-cell {atm_cls}">ATM · {d["atm_status"]}</div>'
        f'<div class="pipe-arrow">→</div>'
        f'<div class="pipe-cell {paa_cls}">PAA · {d["paa_status"]}</div>'
        f"</div>"
    )

    policies = ", ".join(d.get("policies_evaluated", [])) or "—"
    policy_id = d.get("policy_id") or "—"
    policy_version = d.get("policy_version") or "—"
    rationale = d["rationale"]

    approval_row = ""
    if d["approval_required"]:
        outcome = (d.get("approval_outcome") or "pending").upper()
        approval_row = (
            f'<div class="kv" style="margin-top:6px;"><b>Approval</b>: required · outcome '
            f'<code>{outcome}</code></div>'
        )

    cond_row = ""
    if d.get("conditions"):
        cond_row = (
            f'<div class="kv" style="margin-top:6px;"><b>Conditions</b>: '
            f'<code>{", ".join(d["conditions"])}</code></div>'
        )

    st.markdown(
        f"""
        <div class="card">
          <h4>Governance verdict</h4>
          <span class="decision-badge" style="background:{color};">{label}</span>
          {pipe_html}
          <div class="kv" style="margin-top:6px;"><b>Policies evaluated</b>: {policies}</div>
          <div class="kv"><b>Deciding policy</b>: <code>{policy_id}</code> · v{policy_version}</div>
          <div class="kv muted" style="margin-top:8px; line-height:1.45;">{rationale}</div>
          {approval_row}
          {cond_row}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_outcome_card(event: dict) -> None:
    if event["event_type"] != "decision":
        st.markdown(
            f"""
            <div class="card">
              <h4>Result</h4>
              <div class="kv">{event['summary']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    d = event["detail"]
    outcome = d["execution_outcome"]
    executed = d["atm_status"] == "executed"
    status_color = "#2e7d32" if executed else "#c62828"
    status_label = "Executed" if executed else "Aborted"
    st.markdown(
        f"""
        <div class="card">
          <h4>What happened</h4>
          <div class="kv"><b>Status</b>: <span style="color:{status_color}; font-weight:700;">{status_label}</span></div>
          <div class="kv muted" style="margin-top:6px;">{outcome}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Bottom panels (collapsed by default)
# ---------------------------------------------------------------------------


def render_facts_panel(event: dict) -> None:
    if event["event_type"] != "decision":
        st.caption("No facts for a context event.")
        return
    d = event["detail"]
    facts = d.get("facts_used", {})
    if not facts:
        st.caption("No facts recorded.")
        return
    for rule_id, vals in facts.items():
        st.markdown(f"**{rule_id}**")
        st.json(vals, expanded=False)


def render_ledger(events: List[dict], current_seq: int) -> None:
    rows = []
    for e in events:
        if e["event_type"] == "decision":
            d = e["detail"]
            rows.append({
                "#": e["sequence"],
                "kind": "decision",
                "action": d["intended_action"],
                "decision": d["decision"],
                "policy": d.get("policy_id") or "—",
                "approval": d.get("approval_outcome") or ("required" if d["approval_required"] else ""),
                "outcome": d["execution_outcome"][:60],
            })
        else:
            rows.append({
                "#": e["sequence"],
                "kind": e["event_type"],
                "action": "",
                "decision": "",
                "policy": "",
                "approval": "",
                "outcome": e["summary"][:60],
            })
    df = pd.DataFrame(rows)

    def _style(row):
        styles = [""] * len(row)
        if row["#"] == current_seq:
            styles = ["background-color: #fff8e1; font-weight: 600;"] * len(row)
        elif row["kind"] == "decision":
            color = DECISION_COLORS.get(row["decision"], "#444")
            styles = [f"background-color: {color}14;"] * len(row)
        return styles

    st.dataframe(df.style.apply(_style, axis=1), use_container_width=True, hide_index=True)


def render_cockpit(events: List[dict]) -> None:
    records = _decision_records(events)
    delegation = build_consumer_delegation()
    attempted = len(records)
    allowed = sum(1 for r in records if r.decision.value in ("allow", "allow_with_conditions"))
    blocked = sum(1 for r in records if r.decision.value == "block")
    escalated = sum(1 for r in records if r.decision.value == "escalate")
    budget_consumed = 0.0
    discount_captured = 0.0
    for r in records:
        if r.atm_status == "executed" and r.intended_action == "place_order":
            facts = r.facts_used.get("budget.over_ceiling", {})
            budget_consumed += float(facts.get("total_eur", 0.0))
        if r.atm_status == "executed" and r.intended_action == "apply_promotion":
            facts = r.facts_used.get("promotions.must_reduce_total", {})
            discount_captured += float(facts.get("discount_eur", 0.0))

    cols = st.columns(6)
    cols[0].metric("Attempted", attempted)
    cols[1].metric("Allowed", allowed)
    cols[2].metric("Blocked", blocked)
    cols[3].metric("Escalations", escalated)
    cols[4].metric("Budget used", f"€{budget_consumed:,.0f}", f"of €{delegation.budget_ceiling_eur:,.0f}")
    cols[5].metric("Discount", f"€{discount_captured:,.0f}")


def render_mission_summary() -> None:
    d = build_consumer_delegation()
    cols = st.columns(4)
    cols[0].metric("Mission", "Half-marathon shoes")
    cols[1].metric("Budget ceiling", f"€{d.budget_ceiling_eur:,.0f}")
    cols[2].metric("Auto-buy threshold", f"€{d.auto_buy_threshold_eur:,.0f}")
    cols[3].metric("Substitution tolerance", f"{d.substitution_tolerance_pct:.0%}")
    cols = st.columns(4)
    cols[0].metric("Delivery deadline", f"{d.delivery_deadline_days} days")
    cols[1].metric("Min return window", f"{d.min_return_window_days} days")
    cols[2].metric("Forbidden materials", ", ".join(d.forbidden_materials) or "—")
    cols[3].metric("Approved retailers", str(len(d.approved_retailers)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="Governed Agentic Commerce Control Tower",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    st.title("Governed Agentic Commerce Control Tower")
    st.caption(
        "Runtime governance for delegated commerce. Step through one governed action at a time; "
        "the network diagram lights up the live path the action took through the system."
    )

    with st.sidebar:
        st.header("Scenario")
        scenario = st.selectbox(
            "Pick a scripted run",
            options=list(SCENARIO_BUILDERS.keys()),
            format_func=lambda s: SCENARIO_BRIEFS[s].title if s in SCENARIO_BRIEFS else s,
        )
        source = st.radio("Trace source", ["Pre-generated", "Run fresh"], index=0)
        trace_dir = EXAMPLES_DIR if source == "Pre-generated" else RUNTIME_DIR

        if source == "Run fresh":
            if st.button("Run scenario now", use_container_width=True):
                RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
                target = RUNTIME_DIR / f"{scenario}.jsonl"
                if target.exists():
                    target.unlink()
                run_scenario(scenario, out_dir=RUNTIME_DIR)
                st.success(f"ran {scenario}")

        st.divider()
        autoplay = st.toggle("Auto-play", value=False, help="Advance through steps automatically.")
        delay = st.slider("Step delay (s)", 0.3, 3.0, 1.0, 0.1, disabled=not autoplay)

        st.divider()
        with st.expander("Mission detail", expanded=False):
            d = build_consumer_delegation()
            st.json(d.model_dump(mode="json"), expanded=False)

    traces = _load_traces(trace_dir)
    events = traces.get(scenario, [])
    if not events:
        st.warning(
            f"No trace found for `{scenario}`. Either choose **Pre-generated** or click "
            "**Run scenario now** in the sidebar."
        )
        return

    sb = brief(scenario)
    if sb:
        st.markdown(f"### {sb.title}")
        st.markdown(f"*{sb.subtitle}*")
        st.markdown(
            f'<div class="scenario-brief"><b>What to watch:</b> {sb.what_to_watch}<br/>'
            f'<b>Expected:</b> {sb.expected_outcome}</div>',
            unsafe_allow_html=True,
        )

    # ---- Mission summary strip ------------------------------------------
    render_mission_summary()
    st.divider()

    # ---- Stepper --------------------------------------------------------
    n = len(events)
    key = f"step_{scenario}"
    if key not in st.session_state or st.session_state[key] >= n:
        st.session_state[key] = 0

    nav_left, nav_center, nav_right, nav_pad = st.columns([1, 6, 1, 2])
    if nav_left.button("◀ Prev", use_container_width=True, disabled=st.session_state[key] == 0):
        st.session_state[key] -= 1
    if nav_right.button("Next ▶", use_container_width=True, disabled=st.session_state[key] >= n - 1):
        st.session_state[key] += 1
    nav_center.progress((st.session_state[key] + 1) / n, text=f"Step {st.session_state[key] + 1} of {n}")

    event = events[st.session_state[key]]
    seq = event["sequence"]
    label = step_label(scenario, seq, event["summary"])
    st.markdown(f'<div class="step-line"><b>Step {seq}:</b> {label}</div>', unsafe_allow_html=True)

    # ---- Three-column status -------------------------------------------
    c1, c2, c3 = st.columns([1, 1.3, 1])
    with c1:
        render_intent_card(event)
    with c2:
        render_governance_card(event)
    with c3:
        render_outcome_card(event)

    # ---- Network with active path --------------------------------------
    st.markdown("##### Action flow")
    decision_color = "#455a64"
    if event["event_type"] == "decision":
        decision_color = DECISION_COLORS[event["detail"]["decision"]]
    render_network(event, decision_color)

    # ---- Bottom panels --------------------------------------------------
    with st.expander("Decision ledger (all steps)", expanded=False):
        render_ledger(events, seq)
    with st.expander("KPI cockpit", expanded=False):
        render_cockpit(events)
    with st.expander("Facts used for this step (forensic detail)", expanded=False):
        render_facts_panel(event)

    # ---- Auto-play -----------------------------------------------------
    if autoplay and st.session_state[key] < n - 1:
        time.sleep(delay)
        st.session_state[key] += 1
        st.rerun()


if __name__ == "__main__":
    main()
