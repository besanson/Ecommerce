"""A simulated subscription-service-side agent exposed as an MCP server.

Tools registered:
  get_renewal_terms(service)              -> {monthly_eur, billing_period, requires_data_fields}
  confirm_renewal(service, shared_fields) -> {status, service, monthly_eur, billing_period}
  cancel_subscription(service)            -> {status, service}

Like the retailer agent, this server is governance-agnostic. The consumer
side decides whether a tool runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from gacct.mcp.transport import MCPServer


@dataclass
class SubscriptionServiceAgent(MCPServer):
    service_id: str = ""
    display_name: str = ""
    # Service-side current terms — these are the *retailer's* truth and may
    # have drifted away from the consumer's data_baseline.
    monthly_eur: float = 0.0
    billing_period: str = "monthly"
    requires_data_fields: List[str] = field(
        default_factory=lambda: ["payment_token", "billing_email"]
    )

    def __post_init__(self) -> None:
        super().__init__(name=self.service_id)
        self.register_tool(
            "get_renewal_terms",
            self._get_renewal_terms,
            "Return the service's current renewal terms.",
        )
        self.register_tool(
            "confirm_renewal",
            self._confirm_renewal,
            "Confirm a renewal. Only invoked when the governance engine authorizes it.",
        )
        self.register_tool(
            "cancel_subscription",
            self._cancel_subscription,
            "Cancel the subscription. Wrapped by the governance engine on the consumer side.",
        )

    def _get_renewal_terms(self) -> Dict[str, Any]:
        return {
            "service": self.service_id,
            "display_name": self.display_name,
            "monthly_eur": self.monthly_eur,
            "billing_period": self.billing_period,
            "requires_data_fields": list(self.requires_data_fields),
        }

    def _confirm_renewal(self, service: str, shared_fields: List[str]) -> Dict[str, Any]:
        return {
            "status": "renewed",
            "service": service,
            "monthly_eur": self.monthly_eur,
            "billing_period": self.billing_period,
            "shared_fields": list(shared_fields),
        }

    def _cancel_subscription(self, service: str) -> Dict[str, Any]:
        return {"status": "cancelled", "service": service}
