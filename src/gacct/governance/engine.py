from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from gacct.domain.actions import ActionType, ProposedAction
from gacct.domain.approvals import ApprovalOutcome
from gacct.domain.consumer import ShoppingDelegation
from gacct.domain.decisions import Decision, DecisionRecord
from gacct.domain.policies import PolicyPack
from gacct.domain.product import ProductOffer
from gacct.governance.atm import ActionTimeMonitor, ATMState
from gacct.governance.paa import PostActionAudit
from gacct.governance.pag import PAGOutcome, PreActionGate
from gacct.policy.evaluator import EvaluationContext


class GovernanceBypassError(RuntimeError):
    """Raised when an agent or scenario tries to act outside the engine."""


@dataclass
class GovernedOutcome:
    """The result of running a ProposedAction through the engine."""

    decision: Decision
    record: DecisionRecord
    pag: PAGOutcome
    atm: ATMState
    side_effect_result: Any = None


# A side-effect callable executes the actual retailer-side transition. The
# engine never lets one run unless PAG and ATM agreed.
SideEffect = Callable[[ProposedAction], Any]


class GovernanceEngine:
    """The mandatory governance path for every consequential action.

    Agents do not import side-effect functions directly. They call
    `engine.govern(...)` with the proposed action and a side-effect handle.
    The engine runs PAG, requests approval if needed, runs ATM, executes the
    side effect only if ATM authorizes it, and finally hands the run to PAA
    which produces the DecisionRecord. The record is then emitted to the
    caller-supplied recorder callback (typically the trace store).

    There is no `force_execute` or `skip_governance` path. Adding one would
    be a structural design failure.
    """

    def __init__(
        self,
        packs: Dict[str, PolicyPack],
        *,
        on_record: Callable[[DecisionRecord], None],
        approval_resolver: Optional[Callable[[ProposedAction, PAGOutcome], ApprovalOutcome]] = None,
    ):
        self._packs = packs
        self._pag = PreActionGate(packs)
        self._atm = ActionTimeMonitor()
        self._paa = PostActionAudit(packs)
        self._on_record = on_record
        self._approval_resolver = approval_resolver

    # -- Public entry point -------------------------------------------------

    def govern(
        self,
        *,
        scenario_id: str,
        delegation: ShoppingDelegation,
        action: ProposedAction,
        offer: Optional[ProductOffer] = None,
        original_offer: Optional[ProductOffer] = None,
        requested_data_fields: Optional[List[str]] = None,
        extras: Optional[Dict[str, Any]] = None,
        side_effect: Optional[SideEffect] = None,
        condition_check: Optional[Callable[[ProposedAction], bool]] = None,
    ) -> GovernedOutcome:
        self._validate_action(action)

        ctx = EvaluationContext(
            delegation=delegation,
            action=action,
            offer=offer,
            original_offer=original_offer,
            requested_data_fields=list(requested_data_fields or []),
            extras=dict(extras or {}),
        )

        pag = self._pag.evaluate(ctx)
        approval_required = pag.decision == Decision.ESCALATE
        approval_outcome: Optional[ApprovalOutcome] = None
        if approval_required:
            if self._approval_resolver is None:
                approval_outcome = ApprovalOutcome.TIMEOUT
            else:
                approval_outcome = self._approval_resolver(action, pag)

        conditions_satisfied = True
        if pag.decision == Decision.ALLOW_WITH_CONDITIONS:
            conditions_satisfied = condition_check(action) if condition_check else False

        atm = self._atm.authorize(
            decision=pag.decision,
            approval_outcome=approval_outcome,
            conditions_satisfied=conditions_satisfied,
        )

        side_effect_result: Any = None
        if not atm.aborted and side_effect is not None:
            side_effect_result = side_effect(action)
            execution_outcome = self._render_execution(side_effect_result)
        elif not atm.aborted and side_effect is None:
            execution_outcome = "executed (no side effect handle supplied)"
        else:
            execution_outcome = f"not executed: {atm.abort_reason}"

        record = self._paa.build_record(
            scenario_id=scenario_id,
            delegation=delegation,
            action=action,
            pag=pag,
            atm=atm,
            execution_outcome=execution_outcome,
            approval_required=approval_required,
        )
        self._on_record(record)

        return GovernedOutcome(
            decision=pag.decision,
            record=record,
            pag=pag,
            atm=atm,
            side_effect_result=side_effect_result,
        )

    # -- Internals ----------------------------------------------------------

    def _validate_action(self, action: ProposedAction) -> None:
        if not isinstance(action.action_type, ActionType):
            raise GovernanceBypassError(
                "action_type is not a member of ActionType; refusing to govern "
                "an unknown action class"
            )

    @staticmethod
    def _render_execution(result: Any) -> str:
        if result is None:
            return "executed"
        if isinstance(result, str):
            return result
        if isinstance(result, dict) and "status" in result:
            return f"executed: {result['status']}"
        return f"executed: {type(result).__name__}"
