"""Control plane for governed delegated commerce.

Information architecture (top → bottom):

  1. Mission briefing
  2. System map (centerpiece) — drives state from the selected decision row
  3. Decision ledger (clickable)
  4. Commerce cockpit (KPI strip)
  5. Forensics — credibility anchor, opens for the selected decision

The story is governed delegated action, not chat.  Reasoning is one input
into the model, surfaced inside Forensics; it does not dominate the page.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make in-repo gacct importable on Streamlit Cloud without `pip install .`.
_APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_APP_DIR))
sys.path.insert(0, str(_APP_DIR.parent / "src"))
for _mod in list(sys.modules):
    if _mod == "gacct" or _mod.startswith("gacct."):
        del sys.modules[_mod]

from typing import Dict, List, Optional, Tuple  # noqa: E402

import networkx as nx  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from gacct.domain.decisions import DecisionRecord  # noqa: E402
from gacct.intent.parser import parse_consumer_intent  # noqa: E402
from gacct.scenarios.fixtures import DEFAULT_MISSION_TEXT, build_consumer_delegation  # noqa: E402
from gacct.scenarios.runner import SCENARIO_BUILDERS, run_scenario  # noqa: E402
from gacct.trace.store import TraceStore  # noqa: E402
from narrative import SCENARIO_BRIEFS, brief  # noqa: E402


REPO_ROOT = _APP_DIR.parent
EXAMPLES_DIR = REPO_ROOT / "examples" / "traces"
RUNTIME_DIR = REPO_ROOT / "traces" / "runtime"

# Restrained color semantics, no rainbow.
C_ALLOW = "#2e7d32"
C_COND  = "#1565c0"
C_ESC   = "#ef6c00"   # amber
C_BLOCK = "#c62828"
C_NEUTRAL = "#546e7a" # blue-gray, structural
C_NEUTRAL_LIGHT = "#cfd8dc"

DECISION_COLORS = {
    "allow": C_ALLOW,
    "allow_with_conditions": C_COND,
    "escalate": C_ESC,
    "block": C_BLOCK,
}
DECISION_LABELS = {
    "allow": "ALLOWED",
    "allow_with_conditions": "ALLOWED · WITH CONDITIONS",
    "escalate": "REQUIRES CONSUMER APPROVAL",
    "block": "BLOCKED BY POLICY",
}
DECISION_SHORT = {
    "allow": "Allowed",
    "allow_with_conditions": "Conditional",
    "escalate": "Escalated",
    "block": "Blocked",
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _load_traces(trace_dir: Path) -> Dict[str, List[dict]]:
    if not trace_dir.exists():
        return {}
    store = TraceStore.load(trace_dir)
    return {sid: [e.model_dump(mode="json") for e in store.events_for(sid)] for sid in store.all_scenarios()}


def _decision_records(events: List[dict]) -> List[DecisionRecord]:
    return [DecisionRecord.model_validate(e["detail"]) for e in events if e["event_type"] == "decision"]


def _decision_events(events: List[dict]) -> List[dict]:
    return [e for e in events if e["event_type"] == "decision"]


def _mission_event(events: List[dict]) -> Optional[dict]:
    for e in events:
        if e["event_type"] == "mission_opened":
            return e
    return None


def _scenario_aggregate_state(events: List[dict]) -> str:
    """Whole-scenario tone: blocked > escalated > conditional > allowed."""

    decisions = {e["detail"]["decision"] for e in _decision_events(events)}
    if "block" in decisions:
        return "block"
    if "escalate" in decisions:
        return "escalate"
    if "allow_with_conditions" in decisions:
        return "allow_with_conditions"
    return "allow"


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------


CUSTOM_CSS = f"""
<style>
.block-container {{ padding-top: 0.9rem; padding-bottom: 2.5rem; max-width: 1500px; }}

/* Hero band */
.hero {{
  background: linear-gradient(180deg, #1a2530 0%, #243340 100%);
  color: #eceff1;
  padding: 18px 22px;
  border-radius: 10px;
  margin-bottom: 16px;
}}
.hero h1 {{ margin: 0 0 4px 0; font-size: 1.45rem; }}
.hero .sub {{ color: #b0bec5; font-size: 0.92rem; }}
.hero .meta {{ color: #cfd8dc; font-size: 0.82rem; margin-top: 6px; }}

/* Section headers */
.section-h {{
  margin: 18px 0 6px 0;
  padding-bottom: 4px;
  border-bottom: 1px solid #e0e3e7;
  color: #263238;
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}}

/* Cards */
.card {{
  border: 1px solid #e0e3e7;
  border-radius: 10px;
  padding: 14px 16px;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(0,0,0,0.03);
}}
.card h4 {{
  margin: 0 0 8px 0;
  font-size: 0.7rem;
  color: #607d8b;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 700;
}}

/* Mission briefing */
.mission-quote {{
  font-size: 1.02rem;
  color: #1a2530;
  font-style: italic;
  line-height: 1.5;
  border-left: 3px solid {C_NEUTRAL};
  padding: 6px 12px;
}}
.auth-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
.auth-chip {{
  display: inline-flex;
  flex-direction: column;
  background: #f5f7fa;
  border: 1px solid #e0e3e7;
  border-radius: 6px;
  padding: 6px 10px;
  min-width: 130px;
}}
.auth-chip .lbl {{ font-size: 0.62rem; color: #607d8b; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; }}
.auth-chip .val {{ font-size: 0.95rem; color: #1a2530; font-weight: 600; margin-top: 2px; }}

/* Status banners */
.status-banner {{
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 0.9rem;
  margin-top: 8px;
  font-weight: 500;
}}
.status-allow {{ background: #e8f5e9; border-left: 4px solid {C_ALLOW}; color: #1b5e20; }}
.status-cond  {{ background: #e3f2fd; border-left: 4px solid {C_COND};  color: #0d47a1; }}
.status-esc   {{ background: #fff3e0; border-left: 4px solid {C_ESC};   color: #6d3700; }}
.status-block {{ background: #ffebee; border-left: 4px solid {C_BLOCK}; color: #8b1010; }}

/* Decision badge */
.decision-badge {{
  display: inline-block;
  padding: 4px 12px;
  border-radius: 999px;
  color: white;
  font-weight: 700;
  font-size: 0.85rem;
  letter-spacing: 0.04em;
}}

/* SARC strip */
.sarc-strip {{
  display: flex;
  gap: 8px;
  margin-top: 8px;
  margin-bottom: 4px;
}}
.sarc-cell {{
  flex: 1;
  background: #fafbfc;
  border: 1px solid #e0e3e7;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 0.78rem;
  color: #455a64;
}}
.sarc-cell b {{ color: #263238; }}

/* Pipe (PAG/ATM/PAA) */
.pipe {{ display: flex; gap: 6px; align-items: center; margin: 6px 0; }}
.pipe-cell {{
  flex: 1; text-align: center; padding: 6px;
  border-radius: 5px; background: #eceff1;
  font-size: 0.74rem; font-weight: 700; color: #455a64;
}}
.pipe-cell.on   {{ background: {C_ALLOW}; color: white; }}
.pipe-cell.warn {{ background: {C_ESC};   color: white; }}
.pipe-cell.bad  {{ background: {C_BLOCK}; color: white; }}
.pipe-cell.cond {{ background: {C_COND};  color: white; }}
.pipe-arrow {{ color: #b0bec5; font-weight: bold; }}

/* Reasoning lines inside forensics */
.thought-line {{
  border-left: 3px solid #b0bec5;
  padding: 4px 10px;
  margin: 3px 0;
  background: #fafbfc;
  font-size: 0.83rem;
  border-radius: 3px;
}}
.thought-topic {{
  font-size: 0.62rem; color: {C_NEUTRAL};
  text-transform: uppercase; font-weight: 700;
  letter-spacing: 0.06em; margin-right: 6px;
}}
.mcp-line {{
  border-left: 3px solid #00838f;
  padding: 4px 10px;
  margin: 3px 0;
  background: #e0f7fa;
  font-size: 0.8rem;
  border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}}

.muted {{ color: #607d8b; font-size: 0.85rem; }}
.kv {{ font-size: 0.85rem; line-height: 1.5; }}
.kv b {{ color: #37474f; }}

/* Ledger row colors via row pill */
.row-pill {{
  display: inline-block;
  width: 100%;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 700;
  font-size: 0.75rem;
  text-align: center;
  color: white;
}}
</style>
"""


# ---------------------------------------------------------------------------
# System map — the visual centerpiece
# ---------------------------------------------------------------------------


NODE_POSITIONS = {
    "consumer":          (0.05, 0.50),
    "consumer_agent":    (0.27, 0.50),
    "governance":        (0.55, 0.50),
    "approval":          (0.55, 0.93),
    "trace_store":       (0.55, 0.07),
    "retailer_agent":    (0.85, 0.68),
    "payment_boundary":  (0.85, 0.32),
}
NODE_LABELS = {
    "consumer": "Consumer",
    "consumer_agent": "Consumer\nAgent",
    "governance": "Governance\nPAG · ATM · PAA",
    "approval": "Approval\nService",
    "trace_store": "Trace Store\n(evidence)",
    "retailer_agent": "Retailer Agent\n(MCP)",
    "payment_boundary": "Payment Token\nBoundary",
}
EDGES = [
    ("consumer", "consumer_agent",     "delegates"),
    ("consumer_agent", "governance",   "proposes"),
    ("governance", "approval",         "escalates"),
    ("approval", "governance",         "decision"),
    ("governance", "retailer_agent",   "executes"),
    ("governance", "payment_boundary", "charges"),
    ("governance", "trace_store",      "evidences"),
    ("consumer_agent", "retailer_agent", "MCP query"),
    ("retailer_agent", "consumer_agent", "MCP reply"),
]


def _scenario_edge_summary(events: List[dict]) -> Dict[Tuple[str, str], str]:
    """For each edge, derive a single colour reflecting the strongest event
    across the whole scenario. Block > Escalate > Conditional > Allow > Neutral.

    Returns: {(src, dst): color}
    """

    severity = {"block": 4, "escalate": 3, "allow_with_conditions": 2, "allow": 1, "neutral": 0}
    out: Dict[Tuple[str, str], str] = {}

    def bump(s: str, t: str, decision: str) -> None:
        key = (s, t)
        prev = out.get(key, "neutral")
        if severity[decision] > severity[prev]:
            out[key] = decision

    for ev in events:
        et = ev["event_type"]
        if et == "mcp_message":
            d = ev["detail"]
            s = "retailer_agent" if d["sender"].startswith("retailer:") else "consumer_agent"
            r = "retailer_agent" if d["receiver"].startswith("retailer:") else "consumer_agent"
            if s != r:
                bump(s, r, "allow")
        elif et == "decision":
            d = ev["detail"]
            decision = d["decision"]
            action_type = d["intended_action"]
            target = "retailer_agent" if action_type != "use_payment_token" else "payment_boundary"
            bump("consumer_agent", "governance", decision)
            bump("governance", "trace_store", "allow")  # PAA always writes
            if decision == "block":
                pass
            elif decision == "escalate":
                bump("governance", "approval", "escalate")
                bump("approval", "governance", "escalate")
                if d.get("approval_outcome") == "approved":
                    bump("governance", target, "allow")
            else:
                bump("governance", target, decision)
    bump("consumer", "consumer_agent", "allow")
    return {k: DECISION_COLORS[v] if v in DECISION_COLORS else C_NEUTRAL_LIGHT for k, v in out.items()}


def _selected_edge_color(selected: Optional[dict]) -> Tuple[Dict[Tuple[str, str], str], str]:
    """When a decision is selected, override edges to show only the path that
    decision took."""

    if selected is None:
        return {}, C_NEUTRAL
    d = selected["detail"]
    decision = d["decision"]
    color = DECISION_COLORS[decision]
    action_type = d["intended_action"]
    target = "retailer_agent" if action_type != "use_payment_token" else "payment_boundary"
    path = [("consumer", "consumer_agent"), ("consumer_agent", "governance"), ("governance", "trace_store")]
    if decision == "block":
        pass
    elif decision == "escalate":
        path += [("governance", "approval"), ("approval", "governance")]
        if d.get("approval_outcome") == "approved":
            path += [("governance", target)]
    else:
        path += [("governance", target)]
    return {edge: color for edge in path}, color


def render_system_map(events: List[dict], selected: Optional[dict]) -> None:
    if selected is not None:
        edge_color_map, accent = _selected_edge_color(selected)
    else:
        edge_color_map = _scenario_edge_summary(events)
        # Find the strongest color present for governance-node tint
        accent = C_NEUTRAL
        for col in edge_color_map.values():
            if col == C_BLOCK:
                accent = C_BLOCK; break
            if col == C_ESC and accent != C_BLOCK:
                accent = C_ESC
            if col == C_COND and accent not in (C_BLOCK, C_ESC):
                accent = C_COND
            if col == C_ALLOW and accent == C_NEUTRAL:
                accent = C_ALLOW

    g = nx.DiGraph()
    for n in NODE_POSITIONS:
        g.add_node(n)
    for s, t, _label in EDGES:
        g.add_edge(s, t)

    edge_traces = []
    arrow_annotations = []
    for s, t, label in EDGES:
        x0, y0 = NODE_POSITIONS[s]
        x1, y1 = NODE_POSITIONS[t]
        col = edge_color_map.get((s, t))
        is_active = col is not None
        line_color = col if is_active else C_NEUTRAL_LIGHT
        line_width = 4 if is_active else 1.1
        edge_traces.append(go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            mode="lines",
            line=dict(width=line_width, color=line_color),
            hoverinfo="text", text=label, showlegend=False,
        ))
        if is_active:
            arrow_annotations.append(dict(
                ax=x0, ay=y0, x=x1, y=y1, xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=3, arrowsize=1.6, arrowwidth=2, arrowcolor=line_color,
            ))

    node_x, node_y, labels, fill, border = [], [], [], [], []
    for n, (x, y) in NODE_POSITIONS.items():
        node_x.append(x); node_y.append(y); labels.append(NODE_LABELS[n])
        if n == "governance":
            fill.append(accent); border.append("#1a2530")
        elif n == "approval" and selected and selected["detail"]["decision"] == "escalate":
            fill.append(C_ESC); border.append("#1a2530")
        elif n == "trace_store":
            fill.append(C_NEUTRAL); border.append("#1a2530")
        elif n == "consumer":
            fill.append("#37474f"); border.append("#1a2530")
        elif n == "consumer_agent" or n == "retailer_agent":
            fill.append("#1f3a52"); border.append("#0d2233")
        else:
            fill.append(C_NEUTRAL); border.append("#1a2530")

    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        marker=dict(size=66, color=fill, line=dict(width=2, color=border)),
        text=labels, textposition="middle center",
        textfont=dict(size=10, color="white", family="Arial Black"),
        hoverinfo="text", showlegend=False,
    )

    # Legend annotation (top right)
    legend = (
        f"<span style='color:{C_ALLOW}'>● allowed</span> &nbsp; "
        f"<span style='color:{C_ESC}'>● requires approval</span> &nbsp; "
        f"<span style='color:{C_BLOCK}'>● blocked</span> &nbsp; "
        f"<span style='color:{C_COND}'>● conditional</span> &nbsp; "
        f"<span style='color:{C_NEUTRAL}'>● structural</span>"
    )

    fig = go.Figure(data=edge_traces + [node_trace])
    fig.update_layout(
        showlegend=False, margin=dict(l=10, r=10, t=10, b=10), height=340,
        xaxis=dict(range=[-0.05, 1.0], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[0, 1.05], showgrid=False, zeroline=False, visible=False),
        plot_bgcolor="#fafbfc", paper_bgcolor="#fafbfc",
        annotations=arrow_annotations,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown(f"<div style='text-align:right; font-size:0.78rem;'>{legend}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Mission briefing
# ---------------------------------------------------------------------------


def render_mission(events: List[dict]) -> None:
    me = _mission_event(events)
    if me is None:
        return
    mission_text = me["detail"].get("mission_text", "")
    deleg = me["detail"].get("delegation", {})

    cols = st.columns([1.5, 1])
    with cols[0]:
        st.markdown(
            f"""
            <div class="card">
              <h4>Shopper intent · acting on behalf of <code>{deleg.get("consumer_id","")}</code></h4>
              <div class="mission-quote">"{mission_text}"</div>
              <div class="muted" style="margin-top:8px;">
                Parsed from free text by the intent parser. Anything not extracted falls back to
                conservative defaults; the parsing trail is in the technical appendix.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with cols[1]:
        budget = deleg.get("budget_ceiling_eur", "?")
        threshold = deleg.get("auto_buy_threshold_eur", "?")
        delivery = deleg.get("delivery_deadline_days", "?")
        ret = deleg.get("min_return_window_days", "?")
        sub_tol = int(round(deleg.get("substitution_tolerance_pct", 0) * 100))
        materials = ", ".join(deleg.get("forbidden_materials", [])) or "—"
        merchants_in = ", ".join(deleg.get("approved_retailers", []))
        merchants_out = ", ".join(deleg.get("denied_retailers", [])) or "—"
        data_fields = ", ".join(deleg.get("permitted_data_fields", []))
        chips = "".join([
            f'<div class="auth-chip"><span class="lbl">Budget ceiling</span><span class="val">€{budget:g}</span></div>',
            f'<div class="auth-chip"><span class="lbl">Auto-buy threshold</span><span class="val">€{threshold:g}</span></div>',
            f'<div class="auth-chip"><span class="lbl">Delivery deadline</span><span class="val">{delivery}d</span></div>',
            f'<div class="auth-chip"><span class="lbl">Min return window</span><span class="val">{ret}d</span></div>',
            f'<div class="auth-chip"><span class="lbl">Substitution tolerance</span><span class="val">{sub_tol}%</span></div>',
            f'<div class="auth-chip"><span class="lbl">Forbidden materials</span><span class="val">{materials}</span></div>',
        ])
        st.markdown(
            f"""
            <div class="card">
              <h4>Delegated authority</h4>
              <div class="auth-row">{chips}</div>
              <div class="kv" style="margin-top:10px;"><b>Approved retailers</b>: {merchants_in}</div>
              <div class="kv"><b>Denied retailers</b>: {merchants_out}</div>
              <div class="kv"><b>Permitted data fields</b>: {data_fields}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_mission_status_banner(events: List[dict]) -> None:
    state = _scenario_aggregate_state(events)
    records = _decision_records(events)
    n = len(records)
    allowed = sum(1 for r in records if r.decision.value in ("allow", "allow_with_conditions"))
    blocked = sum(1 for r in records if r.decision.value == "block")
    esc = sum(1 for r in records if r.decision.value == "escalate")
    if state == "block":
        cls, msg = "status-block", (
            f"Policy conflict detected · {blocked} action(s) blocked of {n} attempted. "
            "No order placed; consumer data preserved."
        )
    elif state == "escalate":
        cls, msg = "status-esc", (
            f"Consumer approval required · {esc} escalation(s) of {n} actions. "
            "Action proceeded only after explicit approval."
        )
    elif state == "allow_with_conditions":
        cls, msg = "status-cond", (
            f"Allowed under explicit condition · {n} actions, all within delegated authority."
        )
    else:
        cls, msg = "status-allow", (
            f"All within delegated authority · {allowed} action(s) allowed, no escalations, no blocks."
        )
    st.markdown(f'<div class="status-banner {cls}">{msg}</div>', unsafe_allow_html=True)


def render_sarc_strip() -> None:
    st.markdown(
        f"""
        <div class="sarc-strip">
          <div class="sarc-cell"><b>PAG · Pre-Action Gate</b> — checks delegated authority, policy, eligibility <em>before</em> the action.</div>
          <div class="sarc-cell"><b>ATM · Action-Time Monitor</b> — verifies approval state and conditions at the moment of execution.</div>
          <div class="sarc-cell"><b>PAA · Post-Action Audit</b> — writes the structured decision record into the trace.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Decision ledger — clickable rows
# ---------------------------------------------------------------------------


def render_decision_ledger(decisions: List[dict], state_key: str) -> Optional[int]:
    """Render the ledger. Returns the selected row index (0-based) or None."""

    if not decisions:
        st.info("No governed actions in this scenario.")
        return None
    rows = []
    for i, e in enumerate(decisions):
        d = e["detail"]
        rows.append({
            "Time": d["timestamp"].split("T")[1][:8] if "T" in d["timestamp"] else d["timestamp"][:8],
            "Actor": d["actor"],
            "On behalf of": d["acting_on_behalf_of"],
            "Intended action": d["intended_action"],
            "Decision": DECISION_SHORT[d["decision"]],
            "Policy applied": d.get("policy_id") or "—",
            "Approval": "required · " + (d.get("approval_outcome") or "pending") if d["approval_required"] else "—",
            "Governance outcome": d["execution_outcome"][:80],
            "_decision_raw": d["decision"],
        })
    df = pd.DataFrame(rows)

    def _color_decision(val):
        col = DECISION_COLORS.get({"Allowed": "allow", "Conditional": "allow_with_conditions",
                                   "Escalated": "escalate", "Blocked": "block"}.get(val, ""), "#90a4ae")
        return f"background-color: {col}; color: white; font-weight: 700; text-align: center;"

    styled = (
        df.drop(columns=["_decision_raw"])
          .style
          .map(_color_decision, subset=["Decision"])
    )

    event = st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=state_key,
    )
    if event and event.selection and event.selection.rows:
        return event.selection.rows[0]
    return None


# ---------------------------------------------------------------------------
# Commerce cockpit
# ---------------------------------------------------------------------------


def render_cockpit(events: List[dict]) -> None:
    records = _decision_records(events)
    delegation = build_consumer_delegation()
    attempted = len(records)
    allowed = sum(1 for r in records if r.decision.value in ("allow", "allow_with_conditions"))
    blocked = sum(1 for r in records if r.decision.value == "block")
    escalated = sum(1 for r in records if r.decision.value == "escalate")
    approvals = sum(1 for r in records if r.approval_required)
    budget_consumed = 0.0
    discount = 0.0
    for r in records:
        if r.atm_status == "executed" and r.intended_action == "place_order":
            budget_consumed += float(r.facts_used.get("budget.over_ceiling", {}).get("total_eur", 0.0))
        if r.atm_status == "executed" and r.intended_action == "apply_promotion":
            discount += float(r.facts_used.get("promotions.must_reduce_total", {}).get("discount_eur", 0.0))

    cols = st.columns(4)
    cols[0].metric("Actions attempted", attempted)
    cols[1].metric("Allowed", allowed)
    cols[2].metric("Blocked by policy", blocked)
    cols[3].metric("Required approval", approvals)

    cols = st.columns(3)
    cols[0].metric("Escalations triggered", escalated)
    cols[1].metric("Budget consumed", f"€{budget_consumed:,.0f}", f"of €{delegation.budget_ceiling_eur:,.0f} ceiling")
    cols[2].metric("Savings captured", f"€{discount:,.0f}")


# ---------------------------------------------------------------------------
# Forensics — the credibility anchor
# ---------------------------------------------------------------------------


def render_forensics(events: List[dict], selected: dict) -> None:
    """Drill-down for the selected decision row."""

    d = selected["detail"]
    decision = d["decision"]
    color = DECISION_COLORS[decision]
    label = DECISION_LABELS[decision]

    # Find preceding thoughts (everything from the last decision boundary up to this event)
    selected_seq = selected["sequence"]
    block: List[dict] = []
    for e in events:
        if e["sequence"] >= selected_seq:
            break
        if e["event_type"] == "agent_thought":
            block.append(e)
        elif e["event_type"] == "decision":
            block = []  # reset at each prior decision
    # Find the MCP messages closest to this decision (preceding window)
    mcp_window: List[dict] = []
    for e in events:
        if e["sequence"] >= selected_seq:
            break
        if e["event_type"] == "mcp_message":
            mcp_window.append(e)
        elif e["event_type"] == "decision":
            mcp_window = []

    # Header
    st.markdown(
        f"""
        <div class="card" style="margin-bottom: 10px;">
          <h4>Decision evidence · governance verdict</h4>
          <div style="display:flex; align-items:center; gap: 14px; margin-top: 4px;">
            <span class="decision-badge" style="background:{color};">{label}</span>
            <span class="muted">action <code>{d["intended_action"]}</code> · actor <code>{d["actor"]}</code> · on behalf of <code>{d["acting_on_behalf_of"]}</code></span>
          </div>
          <div class="kv" style="margin-top:8px;"><b>Payload</b>: <code>{d["action_payload_summary"]}</code></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Pipeline + facts + outcome
    cols = st.columns([1.1, 1])
    with cols[0]:
        pag_cls = {"allow": "on", "block": "bad", "escalate": "warn", "allow_with_conditions": "cond"}[decision]
        atm_cls = "on" if d["atm_status"] == "executed" else "bad"
        pipe = (
            f'<div class="pipe">'
            f'<div class="pipe-cell {pag_cls}">PAG · {d["pag_status"]}</div>'
            f'<div class="pipe-arrow">→</div>'
            f'<div class="pipe-cell {atm_cls}">ATM · {d["atm_status"]}</div>'
            f'<div class="pipe-arrow">→</div>'
            f'<div class="pipe-cell on">PAA · {d["paa_status"]}</div>'
            f'</div>'
        )
        policies = ", ".join(d.get("policies_evaluated", [])) or "—"
        approval_row = ""
        if d["approval_required"]:
            approval_row = f'<div class="kv"><b>Approval</b>: required · outcome <code>{(d.get("approval_outcome") or "pending").upper()}</code></div>'
        cond_row = ""
        if d.get("conditions"):
            cond_row = f'<div class="kv"><b>Conditions</b>: <code>{", ".join(d["conditions"])}</code></div>'
        st.markdown(
            f"""
            <div class="card">
              <h4>Governance pipeline</h4>
              {pipe}
              <div class="kv" style="margin-top:6px;"><b>Policies evaluated</b>: {policies}</div>
              <div class="kv"><b>Deciding policy</b>: <code>{d.get("policy_id") or "—"}</code> · v{d.get("policy_version") or "—"}</div>
              <div class="kv muted" style="margin-top:6px;">{d["rationale"]}</div>
              {approval_row}
              {cond_row}
            </div>
            """,
            unsafe_allow_html=True,
        )
    with cols[1]:
        executed = d["atm_status"] == "executed"
        outcome_color = C_ALLOW if executed else C_BLOCK
        outcome_label = "Executed" if executed else "Aborted"
        st.markdown(
            f"""
            <div class="card">
              <h4>Outcome &amp; evidence</h4>
              <div class="kv"><b>Status</b>: <span style="color:{outcome_color}; font-weight:700;">{outcome_label}</span></div>
              <div class="kv muted" style="margin-top:4px;">{d["execution_outcome"]}</div>
              <div class="kv" style="margin-top:8px;"><b>Reversible</b>: {'no' if not d["reversible_flag"] else 'yes'}</div>
              <div class="kv"><b>trace_id</b>: <code>{d["trace_id"]}</code></div>
              <div class="kv"><b>scenario_id</b>: <code>{d["scenario_id"]}</code></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Reasoning + MCP context (collapsed)
    cols = st.columns(2)
    with cols[0]:
        if block:
            thoughts = "".join(
                f'<div class="thought-line"><span class="thought-topic">{t["detail"]["topic"]}</span>{t["detail"]["content"]}</div>'
                for t in block
            )
            st.markdown(
                f'<div class="card" style="margin-top:10px;"><h4>Reasoning that led to this action</h4>{thoughts}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="card" style="margin-top:10px;"><h4>Reasoning that led to this action</h4><div class="muted">No prior reasoning recorded for this step.</div></div>',
                unsafe_allow_html=True,
            )
    with cols[1]:
        if mcp_window:
            lines = "".join(
                f'<div class="mcp-line">{e["detail"]["sender"]} → {e["detail"]["receiver"]} · {e["detail"]["method"]} ({e["detail"]["message_type"]})</div>'
                for e in mcp_window
            )
            st.markdown(
                f'<div class="card" style="margin-top:10px;"><h4>MCP context for this action</h4>{lines}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="card" style="margin-top:10px;"><h4>MCP context for this action</h4><div class="muted">No agent-to-agent traffic preceded this step.</div></div>',
                unsafe_allow_html=True,
            )

    with st.expander("Raw decision record", expanded=False):
        st.json(d, expanded=False)
    with st.expander("Facts used", expanded=False):
        st.json(d.get("facts_used") or {}, expanded=False)


# ---------------------------------------------------------------------------
# Technical appendix
# ---------------------------------------------------------------------------


def render_technical_appendix(events: List[dict]) -> None:
    with st.expander("Technical appendix — full event timeline, MCP log, parser trace, raw delegation", expanded=False):
        tabs = st.tabs(["Full timeline", "MCP log", "Parser trace", "Raw delegation"])
        with tabs[0]:
            rows = []
            for e in events:
                rows.append({
                    "#": e["sequence"],
                    "type": e["event_type"],
                    "actor": e["actor"],
                    "summary": e["summary"][:120],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        with tabs[1]:
            mcp = [e for e in events if e["event_type"] == "mcp_message"]
            if not mcp:
                st.caption("No MCP traffic.")
            else:
                rows = []
                for e in mcp:
                    d = e["detail"]
                    rows.append({
                        "#": e["sequence"],
                        "type": d["message_type"],
                        "sender": d["sender"],
                        "receiver": d["receiver"],
                        "method": d["method"],
                        "message_id": d["message_id"],
                        "correlation_id": d.get("correlation_id") or "",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        with tabs[2]:
            me = _mission_event(events)
            if me and me["detail"].get("parsing_trace"):
                for line in me["detail"]["parsing_trace"]:
                    st.markdown(f"- {line}")
            else:
                st.caption("No parser trace.")
        with tabs[3]:
            me = _mission_event(events)
            if me:
                st.json(me["detail"].get("delegation") or {}, expanded=False)


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

    # ---- Sidebar ------------------------------------------------------
    with st.sidebar:
        st.header("Mission")
        scenario = st.selectbox(
            "Scenario",
            options=list(SCENARIO_BUILDERS.keys()),
            format_func=lambda s: SCENARIO_BRIEFS[s].title if s in SCENARIO_BRIEFS else s,
        )
        source = st.radio("Trace source", ["Pre-generated", "Runtime"], index=0,
                          help="Pre-generated traces ship in examples/. Runtime traces are produced by 'Simulate governed mission' below.")
        st.divider()
        st.subheader("Custom mission (optional)")
        intent_text = st.text_area(
            "Consumer says (free text)",
            value=DEFAULT_MISSION_TEXT,
            height=140,
        )
        seed = st.number_input("Random seed", min_value=0, max_value=2**31 - 1, value=42, step=1)
        if st.button("Simulate governed mission", use_container_width=True):
            RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            target = RUNTIME_DIR / f"{scenario}.jsonl"
            if target.exists():
                target.unlink()
            from gacct.scenarios import happy_path, escalation_path, blocked_path, conditional_path
            for mod in (happy_path, escalation_path, blocked_path, conditional_path):
                mod.MISSION_TEXT = intent_text  # type: ignore[attr-defined]
            run_scenario(scenario, out_dir=RUNTIME_DIR, seed=int(seed))
            st.success(f"Simulated {scenario} with seed={seed}")

    trace_dir = EXAMPLES_DIR if source == "Pre-generated" else RUNTIME_DIR
    traces = _load_traces(trace_dir)
    events = traces.get(scenario, [])

    # ---- Hero ---------------------------------------------------------
    sb = brief(scenario)
    state = _scenario_aggregate_state(events) if events else "allow"
    accent = DECISION_COLORS.get(state, C_NEUTRAL)
    st.markdown(
        f"""
        <div class="hero">
          <h1>Governed Agentic Commerce · Control Tower</h1>
          <div class="sub">A runtime control plane for delegated commerce. Consumers grant bounded authority to a shopping agent; every consequential action is intercepted by a SARC-style governance layer that allows, blocks, escalates, or conditionally allows it. Every material decision leaves evidence.</div>
          <div class="meta">Scenario: <b>{sb.title if sb else scenario}</b> &nbsp;·&nbsp; {sb.subtitle if sb else ""} &nbsp;·&nbsp; <span style="color:{accent}; font-weight:700;">{DECISION_LABELS.get(state, '').lower()}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not events:
        st.warning(
            f"No trace for `{scenario}` under `{trace_dir.relative_to(REPO_ROOT)}`. "
            "Choose **Pre-generated** in the sidebar or click **Simulate governed mission**."
        )
        return

    # ---- 1. MISSION ---------------------------------------------------
    st.markdown('<div class="section-h">1 · Mission</div>', unsafe_allow_html=True)
    render_mission(events)
    render_mission_status_banner(events)

    # ---- 2. SYSTEM MAP ------------------------------------------------
    st.markdown('<div class="section-h">2 · System map</div>', unsafe_allow_html=True)
    render_sarc_strip()
    # Selected decision drives the map; default = aggregate scenario view.
    decisions = _decision_events(events)
    selected_key = f"sel_{scenario}_{source}"
    selected_idx = st.session_state.get(selected_key)
    selected_event = decisions[selected_idx] if (selected_idx is not None and 0 <= selected_idx < len(decisions)) else None
    render_system_map(events, selected_event)
    if selected_event is None:
        st.caption("Showing the **whole-scenario** path. Select a row in the ledger below to drill into a single decision.")
    else:
        d = selected_event["detail"]
        st.caption(
            f"Showing the path for the selected action: **{d['intended_action']}** → "
            f"**{DECISION_LABELS[d['decision']].lower()}**. "
            f"Clear the row selection in the ledger to return to the aggregate view."
        )

    # ---- 3. LEDGER ----------------------------------------------------
    st.markdown('<div class="section-h">3 · Governance decisions</div>', unsafe_allow_html=True)
    ledger_key = f"ledger_{scenario}_{source}"
    new_idx = render_decision_ledger(decisions, state_key=ledger_key)
    if new_idx is not None:
        st.session_state[selected_key] = new_idx

    # ---- 4. COCKPIT ---------------------------------------------------
    st.markdown('<div class="section-h">4 · Commerce cockpit</div>', unsafe_allow_html=True)
    render_cockpit(events)

    # ---- 5. FORENSICS -------------------------------------------------
    st.markdown('<div class="section-h">5 · Decision evidence</div>', unsafe_allow_html=True)
    if selected_event is None and decisions:
        # Auto-select the most "interesting" one: prefer block, then escalate, then conditional, then first.
        order = {"block": 0, "escalate": 1, "allow_with_conditions": 2, "allow": 3}
        ranked = sorted(range(len(decisions)), key=lambda i: order[decisions[i]["detail"]["decision"]])
        selected_event = decisions[ranked[0]]
        st.caption("Auto-selected the most consequential decision; click any ledger row above to inspect another.")
    if selected_event is not None:
        render_forensics(events, selected_event)
    else:
        st.info("No decisions to inspect.")

    # ---- Technical appendix -------------------------------------------
    render_technical_appendix(events)


if __name__ == "__main__":
    main()
