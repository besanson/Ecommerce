from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from gacct.domain.actions import ProposedAction
from gacct.domain.consumer import ShoppingDelegation
from gacct.domain.decisions import Decision, DecisionRecord
from gacct.domain.policies import PolicyPack
from gacct.governance.atm import ATMState
from gacct.governance.pag import PAGOutcome


class PostActionAudit:
    """Stage 3 of SARC runtime governance.

    Builds the DecisionRecord that the trace store persists. The audit stage
    is the only writer of canonical decision records - the agents and the UI
    are forbidden to construct them directly. This keeps a single chokepoint
    for audit shape evolution.
    """

    def __init__(self, packs: Optional[Dict[str, PolicyPack]] = None):
        self._packs = packs or {}

    def build_record(
        self,
        *,
        scenario_id: str,
        delegation: ShoppingDelegation,
        action: ProposedAction,
        pag: PAGOutcome,
        atm: ATMState,
        execution_outcome: str,
        approval_required: bool,
    ) -> DecisionRecord:
        deciding_pack, deciding_version, deciding_rule = self._pick_deciding_pack(pag)
        conditions = [v.condition for v in pag.verdicts if v.condition]
        return DecisionRecord(
            trace_id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            actor=action.agent_name,
            acting_on_behalf_of=delegation.acting_on_behalf_of,
            agent_name=action.agent_name,
            action_id=action.action_id,
            intended_action=action.action_type.value,
            action_payload_summary=action.payload_summary(),
            decision=pag.decision,
            rationale=pag.rationale,
            policy_id=deciding_rule or deciding_pack,
            policy_version=deciding_version,
            policies_evaluated=pag.packs_evaluated,
            facts_used=pag.facts,
            pag_status=pag.decision.value,
            atm_status="aborted" if atm.aborted else "executed",
            paa_status="recorded",
            approval_required=approval_required,
            approval_outcome=(atm.approval_outcome.value if atm.approval_outcome else None),
            execution_outcome=execution_outcome,
            reversible_flag=action.reversible,
            conditions=conditions,
            # Pass-through of data-foundation provenance. No semantic change
            # to PAG/ATM/PAA - these fields are populated only when the
            # caller attached a ConsumerContext to the ProposedAction.
            context_id=getattr(action, "context_id", None),
            context_version=getattr(action, "context_version", None),
        )

    def _pick_deciding_pack(self, pag: PAGOutcome):
        """Identify the pack/rule that drove the verdict for the record.

        Returns (pack_id, pack_version, rule_id). Pack version is looked up
        from the loaded pack registry so that the audit field reflects the
        actual YAML version, not a constant.
        """

        if not pag.verdicts:
            return None, None, None
        deciding = next(
            (v for v in pag.verdicts if v.decision == pag.decision and v.decision != Decision.ALLOW),
            None,
        )
        if deciding is None:
            pack_id = pag.packs_evaluated[0] if pag.packs_evaluated else None
            version = self._packs[pack_id].version if pack_id and pack_id in self._packs else None
            return pack_id, version, None
        pack_id = deciding.rule_id.split(".")[0]
        version = self._packs[pack_id].version if pack_id in self._packs else None
        return pack_id, version, deciding.rule_id
