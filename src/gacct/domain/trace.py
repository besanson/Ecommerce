from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """A single sequenced entry in the trace store.

    A DecisionRecord is the canonical artifact of a governed action, but the
    trace also records non-decision events (mission opened, retailer offer
    received, approval requested/granted, scenario completed) so that a
    forensic reviewer can reconstruct context, not just verdicts.
    """

    trace_id: str
    scenario_id: str
    sequence: int = Field(description="Monotonic per scenario_id.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str
    actor: str
    summary: str
    detail: Dict[str, Any] = Field(default_factory=dict)
    prev_hash: Optional[str] = Field(
        default=None,
        description="Hash of the previous event in this scenario. Demo-grade "
        "chaining only - see docs/risk-and-limitations.md.",
    )
    self_hash: Optional[str] = None
