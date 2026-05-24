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
}


def brief(scenario_id: str) -> Optional[ScenarioBrief]:
    return SCENARIO_BRIEFS.get(scenario_id)


# Step label is computed from the event itself in the new UI.
def step_label(scenario_id: str, sequence: int, fallback: str) -> str:  # kept for API compat
    return fallback
