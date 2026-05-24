from __future__ import annotations

import json

from gacct.domain.decisions import Decision, DecisionRecord
from gacct.trace.store import TraceStore


def _fake_record(scenario_id: str, decision=Decision.ALLOW) -> DecisionRecord:
    return DecisionRecord(
        trace_id="t1",
        scenario_id=scenario_id,
        actor="agent:test",
        acting_on_behalf_of="consumer:test",
        agent_name="agent:test",
        action_id="a1",
        intended_action="place_order",
        action_payload_summary="place_order(retailer_id=r1)",
        decision=decision,
        rationale="ok",
        policies_evaluated=["retailers"],
        facts_used={},
        pag_status=decision.value,
        atm_status="executed",
        paa_status="recorded",
        approval_required=False,
        execution_outcome="executed: confirmed",
        reversible_flag=False,
    )


def test_events_chain_with_hashes(tmp_path):
    store = TraceStore(tmp_path)
    e1 = store.record_event(scenario_id="s1", event_type="x", actor="a", summary="first")
    e2 = store.record_event(scenario_id="s1", event_type="x", actor="a", summary="second")
    assert e1.prev_hash is None
    assert e2.prev_hash == e1.self_hash


def test_record_decision_persists_and_round_trips(tmp_path):
    store = TraceStore(tmp_path)
    store.record_decision(_fake_record("s1"))
    store.record_decision(_fake_record("s1", decision=Decision.BLOCK))

    # New store loads the same scenario.
    loaded = TraceStore.load(tmp_path)
    records = loaded.decision_records("s1")
    assert [r.decision for r in records] == [Decision.ALLOW, Decision.BLOCK]


def test_jsonl_one_event_per_line(tmp_path):
    store = TraceStore(tmp_path)
    for _ in range(3):
        store.record_event(scenario_id="s1", event_type="x", actor="a", summary="ok")
    path = tmp_path / "s1.jsonl"
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    assert len(lines) == 3
    for line in lines:
        json.loads(line)  # must parse
