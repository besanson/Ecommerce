from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Decision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ESCALATE = "escalate"
    ALLOW_WITH_CONDITIONS = "allow_with_conditions"
    # Pre-PAG verdict - the data foundation is missing or stale so the action
    # cannot even be evaluated. Issued by gacct.domain.context.DataContextValidator
    # before the engine is engaged. Rules never return this value.
    BLOCK_MISSING_CONTEXT = "block_missing_context"


class DecisionRecord(BaseModel):
    """Persistent record of a single governed action's lifecycle.

    Produced by the Post-Action Audit (PAA) stage and appended to the trace
    store. One record per ProposedAction.
    """

    trace_id: str
    scenario_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str = Field(description="The agent or service that proposed the action.")
    acting_on_behalf_of: str = Field(description="Consumer ID the actor is acting for.")
    agent_name: str
    action_id: str
    intended_action: str
    action_payload_summary: str
    decision: Decision
    rationale: str
    policy_id: Optional[str] = None
    policy_version: Optional[str] = None
    policies_evaluated: List[str] = Field(default_factory=list)
    facts_used: Dict[str, Any] = Field(default_factory=dict)
    pag_status: str = Field(description="Outcome of the Pre-Action Gate.")
    atm_status: str = Field(description="Outcome of the Action-Time Monitor.")
    paa_status: str = Field(description="Outcome of the Post-Action Audit.")
    approval_required: bool
    approval_outcome: Optional[str] = None
    execution_outcome: str
    reversible_flag: bool
    conditions: List[str] = Field(default_factory=list)
    # Data-foundation provenance: which ConsumerContext snapshot was active
    # when this action was decided. Populated by PAA pass-through from the
    # ProposedAction; optional so existing scenarios that don't carry a
    # ConsumerContext continue to work unchanged.
    context_id: Optional[str] = None
    context_version: Optional[int] = None
