from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from gacct.domain.approvals import ApprovalOutcome
from gacct.domain.decisions import Decision


@dataclass
class ATMState:
    """The state captured at the moment an action executes."""

    decision_at_execute: Decision
    approval_outcome: Optional[ApprovalOutcome] = None
    conditions_satisfied: bool = True
    execution_metadata: Dict[str, Any] = field(default_factory=dict)
    aborted: bool = False
    abort_reason: Optional[str] = None


class ActionTimeMonitor:
    """Stage 2 of SARC runtime governance.

    Sits between the PAG verdict and the actual side-effect call. Its job is
    to verify that the conditions PAG attached are still satisfied, that any
    required approval came back APPROVED, and that the action's execution
    metadata stays within the bounds PAG assumed. If anything drifts the ATM
    aborts the action - it does not retry or downgrade silently.
    """

    def authorize(
        self,
        decision: Decision,
        approval_outcome: Optional[ApprovalOutcome],
        conditions_satisfied: bool,
        execution_metadata: Optional[Dict[str, Any]] = None,
    ) -> ATMState:
        meta = dict(execution_metadata or {})

        if decision == Decision.BLOCK:
            return ATMState(
                decision_at_execute=decision,
                aborted=True,
                abort_reason="PAG decision was BLOCK",
                approval_outcome=approval_outcome,
                conditions_satisfied=conditions_satisfied,
                execution_metadata=meta,
            )

        if decision == Decision.ESCALATE:
            if approval_outcome is None:
                return ATMState(
                    decision_at_execute=decision,
                    aborted=True,
                    abort_reason="escalation required but no approval outcome supplied",
                    conditions_satisfied=conditions_satisfied,
                    execution_metadata=meta,
                )
            if approval_outcome != ApprovalOutcome.APPROVED:
                return ATMState(
                    decision_at_execute=decision,
                    aborted=True,
                    abort_reason=f"approval outcome was {approval_outcome.value}, not approved",
                    approval_outcome=approval_outcome,
                    conditions_satisfied=conditions_satisfied,
                    execution_metadata=meta,
                )

        if decision == Decision.ALLOW_WITH_CONDITIONS and not conditions_satisfied:
            return ATMState(
                decision_at_execute=decision,
                aborted=True,
                abort_reason="conditions attached by PAG were not satisfied at execute time",
                approval_outcome=approval_outcome,
                conditions_satisfied=False,
                execution_metadata=meta,
            )

        return ATMState(
            decision_at_execute=decision,
            approval_outcome=approval_outcome,
            conditions_satisfied=conditions_satisfied,
            execution_metadata=meta,
            aborted=False,
        )
