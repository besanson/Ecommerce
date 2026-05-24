"""ConsumerContext and DataContextValidator.

Pillar 2 of the three-pillar thesis: the agent is only as good as the
structured, contextualized consumer data it operates on. ConsumerContext is
the explicit, versioned data foundation. Every governed action carries a
reference (context_id + context_version) so the audit trail proves which
data snapshot was active when the decision was made.

DataContextValidator is a pre-PAG gate that refuses to govern an action
whose context is incomplete or stale for the proposed action type. Missing
data is itself a governance failure mode - silently allowing an action
against a partial context would be unsafe.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Set

from pydantic import BaseModel, Field

from gacct.domain.actions import ActionType
from gacct.domain.decisions import Decision


class ConsumerContext(BaseModel):
    """The structured, versioned data foundation an agent depends on.

    `delegation_parameters` mirror the scenario-specific authority the
    consumer has granted (budget thresholds, approved lists, whitelists).
    `data_baseline` holds the last-known facts the agent uses to reason
    (e.g. last-known prices, billing periods, approved services with a
    version timestamp). `context_version` is a monotone integer that bumps
    on every baseline update; downstream evidence is pinned to it.
    """

    context_id: str
    context_version: int
    consumer_id: str
    mission_id: str
    delegation_parameters: Dict[str, Any] = Field(default_factory=dict)
    data_baseline: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=lambda: time.time())

    # ---- helpers used by the agent and the policy evaluator -------------

    def get(self, *path: str, default: Any = None) -> Any:
        """Walk a key path through delegation_parameters first, then data_baseline."""

        for root in (self.delegation_parameters, self.data_baseline):
            cur: Any = root
            ok = True
            for key in path:
                if isinstance(cur, Mapping) and key in cur:
                    cur = cur[key]
                else:
                    ok = False
                    break
            if ok:
                return cur
        return default

    def bumped(self, **baseline_patch: Any) -> "ConsumerContext":
        """Return a copy with data_baseline patched and version incremented.

        Used when the agent's reasoning produces a new fact worth pinning
        (for example, after applying log_price_drift the baseline price
        should be updated for next time).
        """

        new_baseline = dict(self.data_baseline)
        for k, v in baseline_patch.items():
            new_baseline[k] = v
        return self.model_copy(update={
            "data_baseline": new_baseline,
            "context_version": self.context_version + 1,
        })


@dataclass
class ContextValidationResult:
    """The output of DataContextValidator.

    `decision` is either Decision.ALLOW (validation passed) or
    Decision.BLOCK_MISSING_CONTEXT (validation failed). `missing` carries
    the structured list of missing keys so the resulting decision record
    can explain *why* the action was refused.
    """

    decision: Decision
    missing: List[str]
    rationale: str

    @property
    def passed(self) -> bool:
        return self.decision == Decision.ALLOW


# Map each action type to the dotted-path requirements it imposes on the
# ConsumerContext. The dotted path is checked against either
# `delegation_parameters` or `data_baseline` via ConsumerContext.get.
_REQUIRED_BY_ACTION: Dict[ActionType, List[str]] = {
    ActionType.RENEW_SUBSCRIPTION: [
        "approved_services",
        "approved_services_version",
        "monthly_block_threshold",
        "monthly_escalate_threshold",
    ],
    ActionType.CANCEL_SUBSCRIPTION: [
        "approved_services",
        "approved_services_version",
    ],
    ActionType.ACCEPT_TERMS_CHANGE: [
        "approved_services",
        "approved_services_version",
    ],
    ActionType.SHARE_BILLING_DATA: [
        "billing_data_whitelist",
    ],
}


class DataContextValidator:
    """Pre-PAG check that the data foundation is complete enough to govern."""

    def __init__(self, required_by_action: Optional[Dict[ActionType, List[str]]] = None):
        self._required = required_by_action or _REQUIRED_BY_ACTION

    def validate(
        self,
        *,
        action_type: ActionType,
        context: Optional[ConsumerContext],
    ) -> ContextValidationResult:
        if context is None:
            return ContextValidationResult(
                decision=Decision.BLOCK_MISSING_CONTEXT,
                missing=["<no_context>"],
                rationale=(
                    "ProposedAction was constructed without a ConsumerContext. "
                    "Data foundation is the first governance precondition."
                ),
            )
        required = self._required.get(action_type, [])
        missing: List[str] = []
        for key in required:
            if context.get(key) is None:
                missing.append(key)
        if missing:
            return ContextValidationResult(
                decision=Decision.BLOCK_MISSING_CONTEXT,
                missing=missing,
                rationale=(
                    f"ConsumerContext {context.context_id} v{context.context_version} "
                    f"is missing required fields for action {action_type.value!r}: {missing}."
                ),
            )
        return ContextValidationResult(
            decision=Decision.ALLOW,
            missing=[],
            rationale=(
                f"ConsumerContext {context.context_id} v{context.context_version} "
                f"is complete for action {action_type.value!r}."
            ),
        )

    def required_for(self, action_type: ActionType) -> List[str]:
        return list(self._required.get(action_type, []))
