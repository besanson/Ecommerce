from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml

from gacct.domain.policies import PolicyPack


def load_policy_packs(policies_dir: str | Path) -> Dict[str, PolicyPack]:
    """Load every *.yaml file under policies_dir into a {pack_id: PolicyPack} map.

    The loader is deliberately strict: a malformed pack raises rather than
    being silently skipped. Default-deny on missing inputs only applies at
    evaluation time, not at load time.
    """

    policies_path = Path(policies_dir)
    if not policies_path.is_dir():
        raise FileNotFoundError(f"policies dir not found: {policies_path}")

    packs: Dict[str, PolicyPack] = {}
    for yaml_file in sorted(policies_path.glob("*.yaml")):
        with yaml_file.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        pack = PolicyPack.model_validate(raw)
        if pack.pack_id in packs:
            raise ValueError(f"duplicate pack_id {pack.pack_id!r} in {yaml_file}")
        packs[pack.pack_id] = pack
    return packs


def packs_for_action(packs: Dict[str, PolicyPack], action_type: str) -> List[PolicyPack]:
    """Return the subset of packs that opt in to the given action type."""

    return [p for p in packs.values() if action_type in p.applies_to_actions]
