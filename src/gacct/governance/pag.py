from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from gacct.domain.decisions import Decision
from gacct.domain.policies import PolicyPack
from gacct.policy.evaluator import EvaluationContext, RuleVerdict, combine_verdicts, evaluate_pack
from gacct.policy.loader import packs_for_action


@dataclass
class PAGOutcome:
    """The verdict of the Pre-Action Gate.

    `decision` is the combined verdict across every pack opted into the
    action type. `verdicts` is the per-rule trail used by the audit stage.
    """

    decision: Decision
    rationale: str
    verdicts: List[RuleVerdict]
    packs_evaluated: List[str]
    facts: Dict[str, object]


class PreActionGate:
    """Stage 1 of SARC runtime governance.

    Evaluates policy packs against the proposed action and returns a single
    decision. The PAG never executes the action. It also never has access
    to retailer-side or payment-side effects — those belong to the ATM.
    """

    def __init__(self, packs: Dict[str, PolicyPack]):
        self._packs = packs

    def evaluate(self, ctx: EvaluationContext) -> PAGOutcome:
        applicable = packs_for_action(self._packs, ctx.action.action_type.value)
        if not applicable:
            # No pack opted in. Under default-deny we refuse.
            return PAGOutcome(
                decision=Decision.BLOCK,
                rationale=(
                    f"no policy pack opted in to action {ctx.action.action_type.value!r}; "
                    "default-deny"
                ),
                verdicts=[],
                packs_evaluated=[],
                facts={"action_type": ctx.action.action_type.value},
            )

        all_verdicts: List[RuleVerdict] = []
        facts: Dict[str, object] = {}
        for pack in applicable:
            v = evaluate_pack(pack, ctx)
            all_verdicts.extend(v)
            for verdict in v:
                facts[verdict.rule_id] = verdict.facts

        decision = combine_verdicts(all_verdicts)
        rationale = _summarize(decision, all_verdicts)
        return PAGOutcome(
            decision=decision,
            rationale=rationale,
            verdicts=all_verdicts,
            packs_evaluated=[p.pack_id for p in applicable],
            facts=facts,
        )


def _summarize(decision: Decision, verdicts: List[RuleVerdict]) -> str:
    if not verdicts:
        return "no rules evaluated"
    deciding = [v for v in verdicts if v.decision == decision]
    if not deciding:
        deciding = verdicts
    return " | ".join(f"[{v.rule_id}] {v.rationale}" for v in deciding[:4])
