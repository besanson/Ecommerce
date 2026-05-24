from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from gacct.domain.actions import ProposedAction
from gacct.domain.approvals import ApprovalDecision, ApprovalOutcome, ApprovalRequest
from gacct.governance.pag import PAGOutcome


@dataclass
class ScriptedApprovalPolicy:
    """Scripted approval responses for scenario playback.

    Maps `(action_type, decision_key)` to an ApprovalOutcome. A `default` is
    used when no key matches. This is what lets demo paths be deterministic
    without a human in the loop.
    """

    responses: Dict[str, ApprovalOutcome] = field(default_factory=dict)
    default: ApprovalOutcome = ApprovalOutcome.TIMEOUT

    def resolve(self, action: ProposedAction, pag: PAGOutcome) -> ApprovalOutcome:
        return self.responses.get(action.action_type.value, self.default)


class ApprovalService:
    """Manages approval requests and decisions.

    In a real deployment this would push a notification to a phone, surface
    a card in an app, etc. Here it captures requests and resolves them via a
    pluggable `resolver` callback so scenarios can script consumer behaviour.
    """

    def __init__(self, resolver: Callable[[ProposedAction, PAGOutcome], ApprovalOutcome]):
        self._resolver = resolver
        self._requests: List[ApprovalRequest] = []
        self._decisions: List[ApprovalDecision] = []

    def request_and_resolve(
        self,
        *,
        action: ProposedAction,
        pag: PAGOutcome,
        delegation_id: str,
    ) -> ApprovalOutcome:
        request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            action_id=action.action_id,
            delegation_id=delegation_id,
            summary=action.payload_summary(),
            reason=pag.rationale,
        )
        self._requests.append(request)
        outcome = self._resolver(action, pag)
        self._decisions.append(
            ApprovalDecision(request_id=request.request_id, outcome=outcome)
        )
        return outcome

    @property
    def requests(self) -> List[ApprovalRequest]:
        return list(self._requests)

    @property
    def decisions(self) -> List[ApprovalDecision]:
        return list(self._decisions)
