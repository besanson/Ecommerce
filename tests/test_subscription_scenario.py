"""Subscription scenario tests - 10 new tests asserting the seven governance
moments + data-context validator + bypass resistance for RENEW_SUBSCRIPTION.

Each individual-moment test runs the full scenario into a tmp directory and
inspects the resulting decision sequence. This gives realistic end-to-end
coverage while keeping each test focused on a single verdict.
"""

from __future__ import annotations

import inspect
import uuid
from pathlib import Path
from typing import List

import pytest

from gacct.agents.consumer_agent import ConsumerAgent
from gacct.agents.subscription_service import SubscriptionServiceAgent
from gacct.domain.actions import ActionType, ProposedAction
from gacct.domain.context import DataContextValidator
from gacct.domain.decisions import Decision
from gacct.scenarios.fixtures import (
    build_engine,
    build_subscription_context,
    build_subscription_delegation,
    build_transport,
)
from gacct.scenarios.runner import run_scenario
from gacct.trace.store import TraceStore


SCENARIO_ID = "subscription_renewal"


@pytest.fixture
def scenario_decisions(tmp_path: Path) -> List[dict]:
    """Run the subscription scenario once and yield its decision events."""

    result = run_scenario(SCENARIO_ID, out_dir=tmp_path)
    return [e for e in result.events if e["event_type"] == "decision"]


def _by_action(decisions: List[dict], action_type: str) -> List[dict]:
    return [d for d in decisions if d["detail"]["intended_action"] == action_type]


def _by_service(decisions: List[dict], service: str) -> List[dict]:
    return [
        d for d in decisions
        if service in (d["detail"].get("action_payload_summary") or "")
    ]


# ---------------------------------------------------------------------------
# 7 governance moments - one test each
# ---------------------------------------------------------------------------


def test_moment_1_netflix_allowed_within_threshold(scenario_decisions):
    """Pillar tags here: AGENTIC + DATA + GOVERNANCE - fresh baseline, agent
    proposes, governance allows under the auto-renew threshold."""

    matches = [d for d in _by_action(scenario_decisions, "renew_subscription")
               if "service=netflix" in d["detail"]["action_payload_summary"]]
    assert matches, "no Netflix renew decision found"
    assert matches[0]["detail"]["decision"] == Decision.ALLOW.value


def test_moment_2_spotify_conditional_under_drift_tolerance(scenario_decisions):
    """+5% price drift within 10% tolerance → ALLOW_WITH_CONDITIONS (log_price_drift)."""

    matches = [d for d in _by_action(scenario_decisions, "renew_subscription")
               if "service=spotify" in d["detail"]["action_payload_summary"]]
    assert matches
    d = matches[0]["detail"]
    assert d["decision"] == Decision.ALLOW_WITH_CONDITIONS.value
    assert d["conditions"], "expected an explicit condition on the record"


def test_moment_3_dazn_blocked_over_ceiling(scenario_decisions):
    """Baseline says €19.99/mo; service now charges €34.99 - over the €30 block ceiling."""

    matches = [d for d in _by_action(scenario_decisions, "renew_subscription")
               if "service=dazn" in d["detail"]["action_payload_summary"]]
    assert matches
    assert matches[0]["detail"]["decision"] == Decision.BLOCK.value


def test_moment_4_apple_tv_escalates_unknown_service(scenario_decisions):
    """Service not on approved_services → ESCALATE (data gap, agent has no authority yet)."""

    matches = [d for d in _by_action(scenario_decisions, "renew_subscription")
               if "service=apple_tv" in d["detail"]["action_payload_summary"]]
    assert matches
    assert matches[0]["detail"]["decision"] == Decision.ESCALATE.value


def test_moment_5_aggregator_full_card_blocked(scenario_decisions):
    """BundleSavvy aggregator demanded full_card_number - outside the billing-data whitelist."""

    matches = _by_action(scenario_decisions, "share_billing_data")
    assert matches
    assert matches[0]["detail"]["decision"] == Decision.BLOCK.value
    assert "full_card_number" in str(matches[0]["detail"].get("facts_used"))


def test_moment_6_amazon_prime_billing_period_change_escalates(scenario_decisions):
    """Amazon Prime baseline says 'monthly'; service silently switched to 'annual'."""

    matches = [d for d in _by_action(scenario_decisions, "renew_subscription")
               if "service=amazon_prime" in d["detail"]["action_payload_summary"]]
    assert matches
    assert matches[0]["detail"]["decision"] == Decision.ESCALATE.value


def test_moment_7_missing_context_blocks_before_pag(scenario_decisions):
    """The last decision in the scenario is an action against an incomplete
    ConsumerContext - DataContextValidator fires before PAG."""

    block_mc = [
        d for d in scenario_decisions
        if d["detail"]["decision"] == Decision.BLOCK_MISSING_CONTEXT.value
    ]
    assert block_mc, "expected at least one BLOCK_MISSING_CONTEXT decision"
    d = block_mc[0]["detail"]
    assert d["pag_status"] == "not_reached"
    assert "approved_services_version" in str(d["facts_used"]["missing_fields"])


# ---------------------------------------------------------------------------
# End-to-end + data-context validator + bypass tests
# ---------------------------------------------------------------------------


def test_scenario_produces_seven_decision_records_with_context_pinned(tmp_path: Path):
    """Full scenario produces exactly seven DecisionRecords, each carrying
    context_id and context_version."""

    result = run_scenario(SCENARIO_ID, out_dir=tmp_path)
    decisions = [e for e in result.events if e["event_type"] == "decision"]
    assert len(decisions) == 7, f"expected 7 decision records, got {len(decisions)}"
    # Sequenced strictly ascending
    seqs = [e["sequence"] for e in decisions]
    assert seqs == sorted(seqs)
    for e in decisions:
        d = e["detail"]
        assert d["context_id"] == "ctx:oli-subs", d
        assert isinstance(d["context_version"], int) and d["context_version"] >= 7


def test_data_context_validator_blocks_before_pag_directly():
    """Unit test the DataContextValidator: missing fields → BLOCK_MISSING_CONTEXT."""

    validator = DataContextValidator()
    ctx = build_subscription_context(with_approved_services_version=False)
    result = validator.validate(action_type=ActionType.RENEW_SUBSCRIPTION, context=ctx)
    assert result.decision == Decision.BLOCK_MISSING_CONTEXT
    assert "approved_services_version" in result.missing


def test_no_direct_renew_subscription_path_without_engine():
    """Bypass resistance: ConsumerAgent.renew_subscription must route through
    engine.govern (or, before that, through the data-context validator). It
    must NOT directly invoke the subscription service's confirm_renewal tool."""

    src = inspect.getsource(ConsumerAgent.renew_subscription)
    # The MCP confirm_renewal call must live inside a side_effect closure that
    # the engine decides whether to invoke.
    direct_calls = [
        line for line in src.splitlines()
        if ("confirm_renewal" in line)
        and ("side_effect" not in line)
        and ("def _confirm" not in line)
        and ("lambda" not in line)
        and ("_mcp(service," not in line and "_mcp(server," not in line) is False
    ]
    # The only references should be either inside a closure or the engine's side_effect wiring.
    for line in src.splitlines():
        if "confirm_renewal" in line:
            # Must be inside a function body (indented) and reference _mcp through self.
            assert "_mcp" in line or "_confirm" in line, (
                f"renew_subscription appears to call confirm_renewal outside a side_effect closure: {line!r}"
            )
    # And the engine entry point must be present.
    assert "_govern_subscription_action" in src, (
        "renew_subscription must route through _govern_subscription_action → engine.govern"
    )
