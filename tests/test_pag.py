from __future__ import annotations

import uuid

from gacct.domain.actions import ActionType, ProposedAction
from gacct.domain.decisions import Decision
from gacct.governance.pag import PreActionGate
from gacct.policy.evaluator import EvaluationContext


def _make_action(action_type: ActionType, payload=None, reversible=True):
    return ProposedAction(
        action_id=str(uuid.uuid4()),
        delegation_id="d1",
        agent_name="agent:test",
        action_type=action_type,
        payload=payload or {},
        reversible=reversible,
    )


def test_select_merchant_approved_retailer_allows(policy_packs, delegation, retailers):
    pag = PreActionGate(policy_packs)
    action = _make_action(ActionType.SELECT_MERCHANT, {"retailer_id": "retailer:run_co"})
    ctx = EvaluationContext(delegation=delegation, action=action)
    outcome = pag.evaluate(ctx)
    assert outcome.decision == Decision.ALLOW


def test_select_merchant_denied_retailer_blocks(policy_packs, delegation):
    pag = PreActionGate(policy_packs)
    action = _make_action(ActionType.SELECT_MERCHANT, {"retailer_id": "retailer:shady_kicks"})
    ctx = EvaluationContext(delegation=delegation, action=action)
    outcome = pag.evaluate(ctx)
    assert outcome.decision == Decision.BLOCK


def test_select_merchant_unknown_retailer_blocks(policy_packs, delegation):
    pag = PreActionGate(policy_packs)
    action = _make_action(ActionType.SELECT_MERCHANT, {"retailer_id": "retailer:never_heard_of"})
    ctx = EvaluationContext(delegation=delegation, action=action)
    outcome = pag.evaluate(ctx)
    assert outcome.decision == Decision.BLOCK


def test_place_order_within_budget_allows(policy_packs, delegation, retailers):
    pag = PreActionGate(policy_packs)
    offer = retailers["retailer:run_co"].catalogue[0]
    action = _make_action(
        ActionType.PLACE_ORDER,
        payload={"retailer_id": offer.retailer_id, "sku": offer.sku},
        reversible=False,
    )
    ctx = EvaluationContext(delegation=delegation, action=action, offer=offer)
    outcome = pag.evaluate(ctx)
    assert outcome.decision == Decision.ALLOW


def test_place_order_leather_blocks(policy_packs, delegation, retailers):
    pag = PreActionGate(policy_packs)
    leather = next(
        o for o in retailers["retailer:run_co"].catalogue if "leather" in o.materials
    )
    action = _make_action(ActionType.PLACE_ORDER, reversible=False)
    ctx = EvaluationContext(delegation=delegation, action=action, offer=leather)
    outcome = pag.evaluate(ctx)
    assert outcome.decision == Decision.BLOCK


def test_substitute_outside_tolerance_escalates(policy_packs, delegation, retailers):
    pag = PreActionGate(policy_packs)
    catalogue = retailers["retailer:run_co"].catalogue
    original = next(o for o in catalogue if o.sku == "RC-AERO-1")
    substitute = next(o for o in catalogue if o.sku == "RC-AERO-2")
    action = _make_action(ActionType.ACCEPT_SUBSTITUTE)
    ctx = EvaluationContext(delegation=delegation, action=action, offer=substitute, original_offer=original)
    outcome = pag.evaluate(ctx)
    assert outcome.decision == Decision.ESCALATE


def test_share_data_outside_whitelist_blocks(policy_packs, delegation):
    pag = PreActionGate(policy_packs)
    action = _make_action(
        ActionType.SHARE_CONSUMER_DATA,
        payload={"fields": ["shipping_address", "marketing_consent", "phone_number"]},
        reversible=False,
    )
    ctx = EvaluationContext(
        delegation=delegation,
        action=action,
        requested_data_fields=["shipping_address", "marketing_consent", "phone_number"],
    )
    outcome = pag.evaluate(ctx)
    assert outcome.decision == Decision.BLOCK


def test_payment_above_auto_buy_threshold_escalates(policy_packs, delegation):
    pag = PreActionGate(policy_packs)
    action = _make_action(
        ActionType.USE_PAYMENT_TOKEN,
        payload={"amount_eur": 165.0, "retailer_id": "retailer:run_co"},
        reversible=False,
    )
    ctx = EvaluationContext(delegation=delegation, action=action)
    outcome = pag.evaluate(ctx)
    assert outcome.decision == Decision.ESCALATE


def test_return_window_below_minimum_blocks(policy_packs, delegation, retailers):
    pag = PreActionGate(policy_packs)
    shady_offer = retailers["retailer:shady_kicks"].catalogue[0]
    action = _make_action(ActionType.ACCEPT_RETURN_TERMS)
    ctx = EvaluationContext(delegation=delegation, action=action, offer=shady_offer)
    outcome = pag.evaluate(ctx)
    assert outcome.decision == Decision.BLOCK


def test_promotion_with_extra_data_yields_conditions(policy_packs, delegation, retailers):
    pag = PreActionGate(policy_packs)
    offer = retailers["retailer:run_co"].catalogue[0]
    action = _make_action(
        ActionType.APPLY_PROMOTION,
        payload={
            "discount_eur": 10.0,
            "requires_data_fields": ["marketing_consent"],
            "sku": offer.sku,
        },
    )
    ctx = EvaluationContext(delegation=delegation, action=action, offer=offer)
    outcome = pag.evaluate(ctx)
    assert outcome.decision == Decision.ALLOW_WITH_CONDITIONS
    assert any(v.condition for v in outcome.verdicts if v.condition)


def test_missing_offer_defaults_to_deny(policy_packs, delegation):
    pag = PreActionGate(policy_packs)
    action = _make_action(ActionType.PLACE_ORDER, reversible=False)
    ctx = EvaluationContext(delegation=delegation, action=action, offer=None)
    outcome = pag.evaluate(ctx)
    assert outcome.decision in (Decision.BLOCK, Decision.ESCALATE)
    assert "safe-failure" in outcome.rationale or "default-deny" in outcome.rationale


def test_unmapped_action_type_defaults_to_block(policy_packs, delegation):
    """A pack opted in to a known action only; an action with no opted-in pack
    must default to BLOCK rather than silently allow."""

    # Synthesize an action of a type no pack covers: there is no such action
    # type in the enum (the engine refuses unknown types), but we can verify
    # the same outcome by stripping packs.
    pag = PreActionGate({})
    action = _make_action(ActionType.PLACE_ORDER, reversible=False)
    ctx = EvaluationContext(delegation=delegation, action=action)
    outcome = pag.evaluate(ctx)
    assert outcome.decision == Decision.BLOCK
