from __future__ import annotations

import uuid

import pytest

from gacct.domain.actions import ActionType, ProposedAction
from gacct.domain.approvals import ApprovalOutcome
from gacct.domain.decisions import Decision
from gacct.governance.engine import GovernanceBypassError, GovernanceEngine
from gacct.scenarios.fixtures import build_engine
from gacct.trace.store import TraceStore


def _action(action_type=ActionType.PLACE_ORDER, payload=None, reversible=False):
    return ProposedAction(
        action_id=str(uuid.uuid4()),
        delegation_id="d1",
        agent_name="agent:test",
        action_type=action_type,
        payload=payload or {},
        reversible=reversible,
    )


def test_engine_records_decision_for_every_action(tmp_path, delegation, retailers):
    store = TraceStore(tmp_path)
    engine = build_engine(store)
    offer = retailers["retailer:run_co"].catalogue[0]
    outcome = engine.govern(
        scenario_id="t1",
        delegation=delegation,
        action=_action(ActionType.PLACE_ORDER),
        offer=offer,
        requested_data_fields=["shipping_address", "payment_token_id"],
        side_effect=lambda _a: {"status": "confirmed"},
    )
    assert outcome.decision == Decision.ALLOW
    records = store.decision_records("t1")
    assert len(records) == 1
    assert records[0].acting_on_behalf_of == delegation.consumer_id
    assert records[0].policy_version is None or records[0].policy_version == "1.0.0"


def test_escalation_without_approval_aborts(tmp_path, delegation, retailers):
    """Engine with no approval resolver must abort an escalated action."""

    store = TraceStore(tmp_path)
    engine = build_engine(store, approval_resolver=None)
    # Substitute outside tolerance escalates.
    catalogue = retailers["retailer:run_co"].catalogue
    original = next(o for o in catalogue if o.sku == "RC-AERO-1")
    substitute = next(o for o in catalogue if o.sku == "RC-AERO-2")
    outcome = engine.govern(
        scenario_id="t1",
        delegation=delegation,
        action=_action(ActionType.ACCEPT_SUBSTITUTE),
        offer=substitute,
        original_offer=original,
    )
    assert outcome.decision == Decision.ESCALATE
    assert outcome.atm.aborted is True


def test_escalation_with_approval_executes(tmp_path, delegation, retailers):
    store = TraceStore(tmp_path)

    def approve(_action, _pag):
        return ApprovalOutcome.APPROVED

    engine = build_engine(store, approval_resolver=approve)
    catalogue = retailers["retailer:run_co"].catalogue
    original = next(o for o in catalogue if o.sku == "RC-AERO-1")
    substitute = next(o for o in catalogue if o.sku == "RC-AERO-2")
    side_effect_calls = []
    outcome = engine.govern(
        scenario_id="t1",
        delegation=delegation,
        action=_action(ActionType.ACCEPT_SUBSTITUTE),
        offer=substitute,
        original_offer=original,
        side_effect=lambda a: side_effect_calls.append(a) or {"status": "substitute_accepted"},
    )
    assert outcome.decision == Decision.ESCALATE
    assert outcome.atm.aborted is False
    assert outcome.atm.approval_outcome == ApprovalOutcome.APPROVED
    assert len(side_effect_calls) == 1


def test_blocked_action_never_invokes_side_effect(tmp_path, delegation, retailers):
    store = TraceStore(tmp_path)
    engine = build_engine(store)
    shady_offer = retailers["retailer:shady_kicks"].catalogue[0]
    side_effect_calls = []
    outcome = engine.govern(
        scenario_id="t1",
        delegation=delegation,
        action=_action(ActionType.ACCEPT_RETURN_TERMS),
        offer=shady_offer,
        side_effect=lambda a: side_effect_calls.append(a),
    )
    assert outcome.decision == Decision.BLOCK
    assert side_effect_calls == []
    assert outcome.atm.aborted is True


def test_allow_with_conditions_aborts_when_condition_false(tmp_path, delegation, retailers):
    store = TraceStore(tmp_path)
    engine = build_engine(store)
    offer = retailers["retailer:run_co"].catalogue[0]
    side_effect_calls = []
    outcome = engine.govern(
        scenario_id="t1",
        delegation=delegation,
        action=_action(
            ActionType.APPLY_PROMOTION,
            payload={
                "discount_eur": 10.0,
                "requires_data_fields": ["marketing_consent"],
                "sku": offer.sku,
            },
            reversible=True,
        ),
        offer=offer,
        side_effect=lambda a: side_effect_calls.append(a),
        condition_check=lambda _a: False,
    )
    assert outcome.decision == Decision.ALLOW_WITH_CONDITIONS
    assert outcome.atm.aborted is True
    assert side_effect_calls == []


def test_allow_with_conditions_executes_when_condition_true(tmp_path, delegation, retailers):
    store = TraceStore(tmp_path)
    engine = build_engine(store)
    offer = retailers["retailer:run_co"].catalogue[0]
    outcome = engine.govern(
        scenario_id="t1",
        delegation=delegation,
        action=_action(
            ActionType.APPLY_PROMOTION,
            payload={
                "discount_eur": 10.0,
                "requires_data_fields": ["marketing_consent"],
                "sku": offer.sku,
            },
            reversible=True,
        ),
        offer=offer,
        side_effect=lambda _a: {"status": "promotion_applied"},
        condition_check=lambda _a: True,
    )
    assert outcome.decision == Decision.ALLOW_WITH_CONDITIONS
    assert outcome.atm.aborted is False


def test_decision_record_carries_audit_fields(tmp_path, delegation, retailers):
    store = TraceStore(tmp_path)
    engine = build_engine(store)
    offer = retailers["retailer:run_co"].catalogue[0]
    engine.govern(
        scenario_id="audit-test",
        delegation=delegation,
        action=_action(ActionType.PLACE_ORDER),
        offer=offer,
        requested_data_fields=["shipping_address", "payment_token_id"],
        side_effect=lambda _a: {"status": "confirmed"},
    )
    records = store.decision_records("audit-test")
    assert len(records) == 1
    r = records[0]
    assert r.acting_on_behalf_of == delegation.consumer_id
    assert r.policies_evaluated  # at least one pack was consulted
    assert r.policy_version == "1.0.0"  # versions are looked up from the loaded YAML
    assert r.pag_status in {"allow", "block", "escalate", "allow_with_conditions"}
    assert r.atm_status in {"executed", "aborted"}
    assert r.paa_status == "recorded"
    assert r.reversible_flag is False
    assert r.action_payload_summary.startswith("place_order")
    assert r.scenario_id == "audit-test"


def test_engine_refuses_unknown_action_type(tmp_path, delegation):
    """Structural bypass attempt: an object that quacks like a ProposedAction
    but whose action_type is not in the ActionType enum must be refused at the
    boundary, not silently allowed.
    """

    store = TraceStore(tmp_path)
    engine = build_engine(store)

    class FakeActionType:
        value = "transfer_funds_externally"

    fake = ProposedAction.model_construct(
        action_id="x",
        delegation_id="d1",
        agent_name="agent:rogue",
        action_type=FakeActionType(),  # bypass pydantic enum validation via model_construct
        payload={},
        reversible=False,
    )
    with pytest.raises(GovernanceBypassError):
        engine.govern(scenario_id="bypass", delegation=delegation, action=fake)
