from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ApprovalOutcome(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class ApprovalRequest(BaseModel):
    """Raised when the governance engine escalates an action to the consumer."""

    request_id: str
    action_id: str
    delegation_id: str
    summary: str
    reason: str
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalDecision(BaseModel):
    """The consumer's response to an ApprovalRequest."""

    request_id: str
    outcome: ApprovalOutcome
    note: Optional[str] = None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
