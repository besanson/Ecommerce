from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from gacct.domain.actions import ActionType, ProposedAction
from gacct.domain.consumer import ShoppingDelegation
from gacct.domain.decisions import Decision
from gacct.domain.policies import PolicyPack, PolicyRule
from gacct.domain.product import ProductOffer


@dataclass
class EvaluationContext:
    """All facts available to a rule.

    The evaluator never reaches outside this object for state. Missing or
    None facts cause the relevant rule to default-deny (BLOCK or ESCALATE
    per the rule's on_violation).
    """

    delegation: ShoppingDelegation
    action: ProposedAction
    offer: Optional[ProductOffer] = None
    original_offer: Optional[ProductOffer] = None
    requested_data_fields: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleVerdict:
    rule_id: str
    decision: Decision
    rationale: str
    facts: Dict[str, Any]
    condition: Optional[str] = None


_HANDLERS: Dict[str, Callable[[PolicyRule, EvaluationContext], Tuple[bool, str, Dict[str, Any]]]] = {}


def _handler(kind: str):
    def deco(fn):
        _HANDLERS[kind] = fn
        return fn
    return deco


# ---------------------------------------------------------------------------
# Rule handlers. Each returns (passed, rationale, facts_used).
# When `passed` is False the rule's on_violation determines the Decision.
# Missing facts must produce passed=False with a clear rationale.
# ---------------------------------------------------------------------------


@_handler("total_under_ceiling")
def _total_under_ceiling(rule, ctx):
    offer = ctx.offer
    if offer is None:
        return False, "missing offer; defaulting to deny per safe-failure", {}
    total = offer.total_eur
    ceiling = ctx.delegation.budget_ceiling_eur
    ok = total <= ceiling
    return ok, f"total {total:.2f} EUR {'≤' if ok else '>'} ceiling {ceiling:.2f} EUR", {
        "total_eur": total,
        "ceiling_eur": ceiling,
    }


@_handler("total_under_auto_buy_threshold")
def _total_under_auto_buy_threshold(rule, ctx):
    offer = ctx.offer
    if offer is None:
        return False, "missing offer; defaulting to deny per safe-failure", {}
    total = offer.total_eur
    threshold = ctx.delegation.auto_buy_threshold_eur
    ok = total <= threshold
    return ok, f"total {total:.2f} EUR {'≤' if ok else '>'} auto-buy threshold {threshold:.2f} EUR", {
        "total_eur": total,
        "auto_buy_threshold_eur": threshold,
    }


@_handler("retailer_in_approved_list")
def _retailer_in_approved_list(rule, ctx):
    retailer_id = (ctx.offer.retailer_id if ctx.offer else ctx.action.payload.get("retailer_id"))
    if not retailer_id:
        return False, "missing retailer_id; defaulting to deny per safe-failure", {}
    approved = ctx.delegation.approved_retailers
    ok = retailer_id in approved
    return ok, f"retailer {retailer_id!r} {'in' if ok else 'not in'} approved list", {
        "retailer_id": retailer_id,
        "approved_retailers": list(approved),
    }


@_handler("retailer_not_in_denied_list")
def _retailer_not_in_denied_list(rule, ctx):
    retailer_id = (ctx.offer.retailer_id if ctx.offer else ctx.action.payload.get("retailer_id"))
    if not retailer_id:
        return False, "missing retailer_id; defaulting to deny per safe-failure", {}
    denied = ctx.delegation.denied_retailers
    ok = retailer_id not in denied
    return ok, f"retailer {retailer_id!r} {'not in' if ok else 'in'} denied list", {
        "retailer_id": retailer_id,
        "denied_retailers": list(denied),
    }


@_handler("product_materials_excluded")
def _product_materials_excluded(rule, ctx):
    offer = ctx.offer
    if offer is None:
        return False, "missing offer; defaulting to deny per safe-failure", {}
    forbidden = {m.lower() for m in ctx.delegation.forbidden_materials}
    present = {m.lower() for m in offer.materials}
    overlap = sorted(present & forbidden)
    ok = not overlap
    return ok, (
        f"forbidden materials present: {overlap}" if not ok else "no forbidden materials present"
    ), {
        "product_materials": sorted(present),
        "forbidden_materials": sorted(forbidden),
        "overlap": overlap,
    }


@_handler("substitute_within_price_tolerance")
def _substitute_within_price_tolerance(rule, ctx):
    offer = ctx.offer
    original = ctx.original_offer
    if offer is None or original is None:
        return False, "missing offer or original offer; defaulting to deny", {}
    tol = ctx.delegation.substitution_tolerance_pct
    if original.price_eur <= 0:
        return False, "original price ≤ 0; cannot compute variance", {}
    variance = abs(offer.price_eur - original.price_eur) / original.price_eur
    ok = variance <= tol
    return ok, (
        f"price variance {variance:.2%} {'≤' if ok else '>'} tolerance {tol:.0%}"
    ), {
        "variance_pct": round(variance, 4),
        "tolerance_pct": tol,
        "original_price_eur": original.price_eur,
        "substitute_price_eur": offer.price_eur,
    }


@_handler("shipping_within_deadline")
def _shipping_within_deadline(rule, ctx):
    offer = ctx.offer
    if offer is None:
        return False, "missing offer; defaulting to deny", {}
    deadline = ctx.delegation.delivery_deadline_days
    days = offer.shipping_days
    ok = days <= deadline
    return ok, f"shipping {days}d {'≤' if ok else '>'} deadline {deadline}d", {
        "shipping_days": days,
        "deadline_days": deadline,
    }


@_handler("requested_fields_within_whitelist")
def _requested_fields_within_whitelist(rule, ctx):
    requested = list(ctx.requested_data_fields)
    if not requested and ctx.offer is not None:
        requested = list(ctx.offer.terms.requires_data_fields)
    if not requested:
        # No data is being shared; vacuously true.
        return True, "no consumer data fields requested", {"requested_fields": []}
    whitelist = set(ctx.delegation.permitted_data_fields)
    extra = sorted(set(requested) - whitelist)
    ok = not extra
    return ok, (
        f"requested fields outside whitelist: {extra}"
        if not ok
        else "all requested fields within whitelist"
    ), {
        "requested_fields": sorted(set(requested)),
        "permitted_data_fields": sorted(whitelist),
        "extra_fields": extra,
    }


@_handler("payment_under_auto_buy_threshold")
def _payment_under_auto_buy_threshold(rule, ctx):
    amount = ctx.action.payload.get("amount_eur")
    if amount is None:
        return False, "missing amount_eur on payment action; defaulting to deny", {}
    threshold = ctx.delegation.auto_buy_threshold_eur
    ok = amount <= threshold
    return ok, f"payment {amount:.2f} EUR {'≤' if ok else '>'} auto-buy threshold {threshold:.2f} EUR", {
        "amount_eur": amount,
        "auto_buy_threshold_eur": threshold,
    }


@_handler("return_window_meets_minimum")
def _return_window_meets_minimum(rule, ctx):
    offer = ctx.offer
    if offer is None:
        return False, "missing offer; defaulting to deny", {}
    window = offer.terms.return_window_days
    minimum = ctx.delegation.min_return_window_days
    ok = window >= minimum
    return ok, f"return window {window}d {'≥' if ok else '<'} minimum {minimum}d", {
        "return_window_days": window,
        "min_return_window_days": minimum,
    }


@_handler("promotion_reduces_total")
def _promotion_reduces_total(rule, ctx):
    offer = ctx.offer
    discount = ctx.action.payload.get("discount_eur")
    if discount is None and offer is not None:
        discount = offer.terms.promotion_discount_eur
    if discount is None:
        return False, "missing discount_eur; defaulting to deny", {}
    ok = discount > 0
    return ok, f"promotion discount {discount:.2f} EUR {'reduces' if ok else 'does not reduce'} total", {
        "discount_eur": discount,
    }


@_handler("promotion_without_extra_data_sharing")
def _promotion_without_extra_data_sharing(rule, ctx):
    requested = ctx.action.payload.get("requires_data_fields", [])
    whitelist = set(ctx.delegation.permitted_data_fields)
    extra = sorted(set(requested) - whitelist)
    ok = not extra
    return ok, (
        f"promotion requires extra data fields: {extra}"
        if not ok
        else "promotion requires no extra data fields"
    ), {
        "requested_fields": sorted(set(requested)),
        "extra_fields": extra,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_ON_VIOLATION_TO_DECISION = {
    "block": Decision.BLOCK,
    "escalate": Decision.ESCALATE,
    "allow_with_conditions": Decision.ALLOW_WITH_CONDITIONS,
}


def evaluate_pack(pack: PolicyPack, ctx: EvaluationContext) -> List[RuleVerdict]:
    """Run every applicable rule in `pack` against `ctx`.

    Rules whose `kind` has no registered handler return an explicit
    safe-failure verdict (BLOCK). This prevents silent allows when a YAML
    pack references an unimplemented rule kind.
    """

    if ctx.action.action_type.value not in pack.applies_to_actions:
        return []

    verdicts: List[RuleVerdict] = []
    for rule in pack.rules:
        handler = _HANDLERS.get(rule.kind)
        if handler is None:
            verdicts.append(
                RuleVerdict(
                    rule_id=rule.rule_id,
                    decision=Decision.BLOCK,
                    rationale=f"no handler registered for rule kind {rule.kind!r}; safe-failure block",
                    facts={"rule_kind": rule.kind},
                )
            )
            continue

        passed, rationale, facts = handler(rule, ctx)
        if passed:
            verdicts.append(
                RuleVerdict(
                    rule_id=rule.rule_id,
                    decision=Decision.ALLOW,
                    rationale=rationale,
                    facts=facts,
                )
            )
        else:
            decision = _ON_VIOLATION_TO_DECISION.get(rule.on_violation, Decision.BLOCK)
            verdicts.append(
                RuleVerdict(
                    rule_id=rule.rule_id,
                    decision=decision,
                    rationale=rationale,
                    facts=facts,
                    condition=rule.condition if decision == Decision.ALLOW_WITH_CONDITIONS else None,
                )
            )
    return verdicts


def combine_verdicts(verdicts: List[RuleVerdict]) -> Decision:
    """Combine rule verdicts into a single decision.

    Precedence (strictest wins): BLOCK > ESCALATE > ALLOW_WITH_CONDITIONS > ALLOW.
    This precedence is the heart of default-deny under ambiguity: any rule that
    refuses to allow has the last word.
    """

    if not verdicts:
        # No rule opined → no permission. Default deny.
        return Decision.BLOCK

    decisions = {v.decision for v in verdicts}
    if Decision.BLOCK in decisions:
        return Decision.BLOCK
    if Decision.ESCALATE in decisions:
        return Decision.ESCALATE
    if Decision.ALLOW_WITH_CONDITIONS in decisions:
        return Decision.ALLOW_WITH_CONDITIONS
    return Decision.ALLOW


def known_action_types() -> List[str]:
    return [a.value for a in ActionType]
