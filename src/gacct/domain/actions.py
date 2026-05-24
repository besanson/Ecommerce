from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Enumerates every consequential action this control tower governs.

    Only the actions listed here can flow through the governance layer.
    Anything not listed must be either non-consequential (and outside scope)
    or a design error — the engine refuses unknown action types.
    """

    PLACE_ORDER = "place_order"
    USE_PAYMENT_TOKEN = "use_payment_token"
    SHARE_CONSUMER_DATA = "share_consumer_data"
    ACCEPT_SUBSTITUTE = "accept_substitute"
    ACCEPT_RETURN_TERMS = "accept_return_terms"
    APPLY_PROMOTION = "apply_promotion"
    UPGRADE_SHIPPING = "upgrade_shipping"
    SELECT_MERCHANT = "select_merchant"


class ProposedAction(BaseModel):
    """An action a consumer agent wants to take.

    The action does not execute until the governance engine returns an
    ALLOW or ALLOW_WITH_CONDITIONS decision.
    """

    action_id: str
    delegation_id: str
    agent_name: str
    action_type: ActionType
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured action payload. Schema depends on action_type.",
    )
    reversible: bool = Field(
        description="Whether the consequence can be reversed by the consumer "
        "agent without external coordination. Drives audit treatment, not the "
        "allow/block decision itself.",
    )
    rationale: Optional[str] = Field(
        default=None,
        description="Why the consumer agent proposes this action. Recorded for "
        "audit; not used as a policy input.",
    )

    def payload_summary(self) -> str:
        """A short string suitable for the ledger / forensics view."""

        if not self.payload:
            return self.action_type.value
        keys = sorted(self.payload.keys())
        bits = []
        for k in keys:
            v = self.payload[k]
            if isinstance(v, (int, float, str, bool)):
                bits.append(f"{k}={v}")
            else:
                bits.append(f"{k}=<{type(v).__name__}>")
        return f"{self.action_type.value}({', '.join(bits)})"
