"""Per-scenario narrative metadata.

The trace store records *what* happened. The narrative tells the human *why*
this step exists in the scripted demo and what to watch for. Keyed by
scenario_id and the sequence number assigned by the trace store.

Keeping narrative out of the trace keeps the trace machine-readable; keeping
it in code (not YAML) keeps it next to the scenarios it describes.
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


SCENARIO_BRIEFS: Dict[str, ScenarioBrief] = {
    "happy_path": ScenarioBrief(
        title="Happy path",
        subtitle="Approved retailer · compliant product · within budget",
        what_to_watch=(
            "Every consequential action passes through the governance layer and "
            "returns ALLOW. Nothing is silently auto-approved — every step is "
            "evidenced. Watch the ledger grow row by row."
        ),
        expected_outcome="5 actions, all ALLOW. Order is placed; payment token used.",
    ),
    "escalation_path": ScenarioBrief(
        title="Escalation path",
        subtitle="Substitute outside tolerance · total above auto-buy threshold",
        what_to_watch=(
            "The retailer proposes a substitute SKU +14% above the original. "
            "Two policy packs disagree with the agent at once: the substitution "
            "pack escalates the substitute, and the budget pack notices the new "
            "total is above the auto-buy threshold and also escalates. The "
            "scripted approval policy approves; the order then proceeds."
        ),
        expected_outcome="2–3 ESCALATE verdicts; consumer approves; order completes at €165.",
    ),
    "blocked_path": ScenarioBrief(
        title="Blocked path",
        subtitle="Denied retailer · excess data sharing · weak return terms",
        what_to_watch=(
            "Three independent things the agent tries to do; each fails for a "
            "different reason. The retailer-side `confirm_order` is never "
            "invoked. Every refusal is evidenced with the policy that fired."
        ),
        expected_outcome="3 BLOCK verdicts. No order placed. No data shared.",
    ),
    "conditional_path": ScenarioBrief(
        title="Allow-with-conditions path",
        subtitle="Loyalty promotion · requires marketing consent",
        what_to_watch=(
            "A promotion would reduce total spend but requires marketing "
            "consent — a data field outside the consumer's whitelist. The "
            "promotions pack returns ALLOW_WITH_CONDITIONS; the consumer's "
            "explicit `loyalty_enrollment_accepted` flag is the condition. "
            "ATM verifies it at execute time."
        ),
        expected_outcome="1 ALLOW_WITH_CONDITIONS, condition met, order completes.",
    ),
}


# Per-step short labels keyed by (scenario_id, sequence). Falls back to the
# trace event's own summary if a step isn't pre-described.
STEP_LABELS: Dict[tuple, str] = {
    ("happy_path", 1): "Consumer opens the mission and delegates to the shopping agent.",
    ("happy_path", 2): "Agent searches the approved retailer and shortlists a compliant offer.",
    ("happy_path", 3): "Agent picks the retailer. Governance checks approved/denied lists.",
    ("happy_path", 4): "Agent accepts the retailer's return terms (30 days vs 14-day minimum).",
    ("happy_path", 5): "Agent shares only whitelisted data fields with the retailer.",
    ("happy_path", 6): "Agent places the order. Budget pack confirms €145 ≤ €180 ceiling.",
    ("happy_path", 7): "Agent charges the payment token. Auto-buy pack confirms within threshold.",
    ("happy_path", 8): "Mission complete.",

    ("escalation_path", 1): "Consumer opens the mission.",
    ("escalation_path", 2): "Retailer returns the original and proposes a +14% substitute.",
    ("escalation_path", 3): "Agent selects the approved retailer.",
    ("escalation_path", 4): "Agent tries to accept the substitute. Substitution and budget packs both fire.",
    ("escalation_path", 5): "Agent accepts the substitute's return terms.",
    ("escalation_path", 6): "Agent shares whitelisted data fields.",
    ("escalation_path", 7): "Agent places the order — total exceeds auto-buy threshold; escalates.",
    ("escalation_path", 8): "Payment token charge above threshold; escalates and is approved.",
    ("escalation_path", 9): "Mission complete after consumer approvals.",

    ("blocked_path", 1): "Consumer opens the mission.",
    ("blocked_path", 2): "Agent tries to select a denied retailer (Shady Kicks).",
    ("blocked_path", 3): "Agent tries to share marketing_consent + phone_number with Trail Works.",
    ("blocked_path", 4): "Agent tries to accept a 3-day return window vs 14-day minimum.",
    ("blocked_path", 5): "Mission ends without any order placed.",

    ("conditional_path", 1): "Consumer opens the mission with a loyalty promo on the table.",
    ("conditional_path", 2): "Agent selects the approved retailer.",
    ("conditional_path", 3): "Agent accepts the retailer's return terms.",
    ("conditional_path", 4): "Agent attempts the loyalty promotion — requires marketing_consent.",
    ("conditional_path", 5): "Agent shares whitelisted data fields.",
    ("conditional_path", 6): "Agent places the order.",
    ("conditional_path", 7): "Agent charges the payment token.",
    ("conditional_path", 8): "Mission complete.",
}


def step_label(scenario_id: str, sequence: int, fallback: str) -> str:
    return STEP_LABELS.get((scenario_id, sequence), fallback)


def brief(scenario_id: str) -> Optional[ScenarioBrief]:
    return SCENARIO_BRIEFS.get(scenario_id)
