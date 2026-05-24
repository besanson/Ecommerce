"""Per-scenario narrative metadata.

The trace store records *what* happened. The narrative tells the human *why*
this scenario exists and what to watch for. Step labels are sourced from the
trace event itself (mission_opened, agent_thought, mcp_message, decision,
scenario_completed) so the timeline reads naturally — no per-sequence
mapping needed in this version.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ScenarioBrief:
    title: str
    subtitle: str
    what_to_watch: str
    expected_outcome: str


# Per-action pillar tags. The three-pillar thesis is visible in the UI's
# ledger via these tags. Each entry: ActionType.value -> list of pillar tags.
ACTION_PILLAR_TAGS: Dict[str, list] = {
    # Shopping-domain actions
    "select_merchant":     ["AGENTIC", "GOVERNANCE"],
    "accept_substitute":   ["AGENTIC", "GOVERNANCE"],
    "accept_return_terms": ["GOVERNANCE"],
    "share_consumer_data": ["DATA", "GOVERNANCE"],
    "apply_promotion":     ["AGENTIC", "DATA", "GOVERNANCE"],
    "upgrade_shipping":    ["AGENTIC", "GOVERNANCE"],
    "place_order":         ["AGENTIC", "GOVERNANCE"],
    "use_payment_token":   ["GOVERNANCE"],
    # Subscription-domain actions — every one of these depends on the
    # ConsumerContext baseline being fresh, so all carry the DATA tag.
    "renew_subscription":  ["AGENTIC", "DATA", "GOVERNANCE"],
    "cancel_subscription": ["AGENTIC", "GOVERNANCE"],
    "accept_terms_change": ["DATA", "GOVERNANCE"],
    "share_billing_data":  ["DATA", "GOVERNANCE"],
}


def pillar_tags(action_type: str) -> list:
    return ACTION_PILLAR_TAGS.get(action_type, [])


SCENARIO_BRIEFS: Dict[str, ScenarioBrief] = {
    "happy_path": ScenarioBrief(
        title="Happy path",
        subtitle="Mission parsed · approved retailer · compliant product · within budget",
        what_to_watch=(
            "Walk through the agent's reasoning, then the MCP calls to the retailer, "
            "then every governed action. Every decision returns ALLOW; the retailer's "
            "confirm_order tool runs only after the engine authorizes it."
        ),
        expected_outcome="5 governed actions, all ALLOW. Order is placed; payment token used.",
    ),
    "escalation_path": ScenarioBrief(
        title="Escalation path",
        subtitle="Substitute outside tolerance · total above auto-buy threshold",
        what_to_watch=(
            "The agent asks the retailer for a substitute via MCP. Reasoning predicts "
            "two escalations (substitution variance + budget). The scripted approval "
            "policy approves; order completes at €165."
        ),
        expected_outcome="Multiple ESCALATE verdicts; consumer approves; order completes.",
    ),
    "blocked_path": ScenarioBrief(
        title="Blocked path",
        subtitle="Denied retailer · excess data sharing · weak return terms",
        what_to_watch=(
            "Three independent governance failures. Each is preceded by reasoning that "
            "explicitly predicts the BLOCK, and each fails on a different policy. "
            "confirm_order is never invoked over MCP."
        ),
        expected_outcome="3 BLOCK verdicts. No order. No data shared.",
    ),
    "conditional_path": ScenarioBrief(
        title="Allow-with-conditions path",
        subtitle="Loyalty promotion · requires marketing consent",
        what_to_watch=(
            "Promotion would reduce total but requires marketing_consent. PAG returns "
            "ALLOW_WITH_CONDITIONS; the consumer's explicit opt-in flag is what ATM "
            "checks at execute time."
        ),
        expected_outcome="1 ALLOW_WITH_CONDITIONS; condition met; order completes.",
    ),
    "subscription_renewal": ScenarioBrief(
        title="Subscription renewal · seven moments",
        subtitle="Three pillars side-by-side — agentic action · curated data · governance",
        what_to_watch=(
            "An end-to-end portfolio renewal exercising all three pillars. Each row "
            "in the ledger carries [AGENTIC] [DATA] [GOVERNANCE] tags showing which "
            "pillar(s) the moment demonstrates. The final row is BLOCK_MISSING_CONTEXT "
            "— the data foundation is itself a governance precondition."
        ),
        expected_outcome=(
            "7 governance moments: 1 ALLOW, 1 ALLOW_WITH_CONDITIONS, 2 BLOCK, 2 "
            "ESCALATE, 1 BLOCK_MISSING_CONTEXT. context_version pinned on every record."
        ),
    ),
}


def brief(scenario_id: str) -> Optional[ScenarioBrief]:
    return SCENARIO_BRIEFS.get(scenario_id)


# Step label is computed from the event itself in the new UI.
def step_label(scenario_id: str, sequence: int, fallback: str) -> str:  # kept for API compat
    return fallback
