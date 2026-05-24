from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PolicyRule(BaseModel):
    """A single rule inside a PolicyPack.

    The rule is intentionally declarative: the evaluator interprets `kind` and
    `params`. Adding a new rule type requires both a YAML edit and an evaluator
    handler - this is deliberate, to keep policy surface area inspectable.
    """

    rule_id: str
    kind: str = Field(
        description="Discriminator interpreted by the evaluator. See "
        "gacct.policy.evaluator for the supported kinds."
    )
    params: Dict[str, Any] = Field(default_factory=dict)
    on_violation: str = Field(
        default="block",
        description="One of 'block', 'escalate', 'allow_with_conditions'.",
    )
    condition: Optional[str] = Field(
        default=None,
        description="Free-form human-readable condition string, used only when "
        "on_violation == 'allow_with_conditions'.",
    )
    description: str


class PolicyPack(BaseModel):
    """A versioned, human-readable bundle of rules.

    Packs are loaded from YAML files in the policies/ directory. They are
    addressable by `pack_id` and carry a `version` so a DecisionRecord can
    point at the exact pack that produced it.
    """

    pack_id: str
    version: str
    title: str
    description: str
    applies_to_actions: List[str] = Field(
        description="Action types this pack opts in to evaluating. Other action "
        "types are skipped by this pack."
    )
    rules: List[PolicyRule]
