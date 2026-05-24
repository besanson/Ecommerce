from __future__ import annotations

from gacct.domain.decisions import Decision
from gacct.scenarios.runner import SCENARIO_BUILDERS, run_scenario


def _decisions(result):
    return [e for e in result.events if e["event_type"] == "decision"]


def test_happy_path_only_allows(tmp_path):
    result = run_scenario("happy_path", out_dir=tmp_path)
    decisions = _decisions(result)
    assert decisions, "happy path produced no decision events"
    for d in decisions:
        assert d["detail"]["decision"] == Decision.ALLOW.value, (
            f"happy path produced non-allow decision: {d['detail']['intended_action']} -> {d['detail']['decision']}"
        )


def test_blocked_path_contains_blocks(tmp_path):
    result = run_scenario("blocked_path", out_dir=tmp_path)
    decisions = _decisions(result)
    assert any(d["detail"]["decision"] == Decision.BLOCK.value for d in decisions)
    # No order_confirmed side effect should appear in execution_outcome
    for d in decisions:
        assert "confirmed" not in d["detail"]["execution_outcome"].lower()


def test_escalation_path_contains_escalations(tmp_path):
    result = run_scenario("escalation_path", out_dir=tmp_path)
    decisions = _decisions(result)
    escs = [d for d in decisions if d["detail"]["decision"] == Decision.ESCALATE.value]
    assert escs, "escalation path produced no ESCALATE decision"
    # And once approved, at least one action proceeded.
    approved = [d for d in escs if d["detail"]["approval_outcome"] == "approved"]
    assert approved


def test_conditional_path_contains_allow_with_conditions(tmp_path):
    result = run_scenario("conditional_path", out_dir=tmp_path)
    decisions = _decisions(result)
    awc = [d for d in decisions if d["detail"]["decision"] == Decision.ALLOW_WITH_CONDITIONS.value]
    assert awc, "conditional path produced no ALLOW_WITH_CONDITIONS"


def test_every_scenario_records_acting_on_behalf_of(tmp_path):
    for sid in SCENARIO_BUILDERS:
        result = run_scenario(sid, out_dir=tmp_path / sid)
        for d in _decisions(result):
            assert d["detail"]["acting_on_behalf_of"].startswith("consumer:")
            assert d["detail"]["policies_evaluated"], (
                f"{sid}/{d['detail']['intended_action']}: missing policies_evaluated"
            )
