from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List

from gacct.approvals.service import ScriptedApprovalPolicy
from gacct.domain.approvals import ApprovalOutcome
from gacct.governance.engine import GovernanceEngine
from gacct.mcp.transport import MCPTransport
from gacct.scenarios import blocked_path, conditional_path, escalation_path, happy_path
from gacct.scenarios.fixtures import build_engine, build_transport
from gacct.trace.store import TraceStore


@dataclass
class ScenarioResult:
    scenario_id: str
    trace_path: Path
    events: List[dict]


SCENARIO_BUILDERS: Dict[str, tuple[Callable[[GovernanceEngine, TraceStore, MCPTransport, int], None], ScriptedApprovalPolicy]] = {
    happy_path.SCENARIO_ID: (
        happy_path.run,
        ScriptedApprovalPolicy(responses={}, default=ApprovalOutcome.REJECTED),
    ),
    escalation_path.SCENARIO_ID: (
        escalation_path.run,
        ScriptedApprovalPolicy(
            responses={
                "accept_substitute": ApprovalOutcome.APPROVED,
                "place_order": ApprovalOutcome.APPROVED,
                "use_payment_token": ApprovalOutcome.APPROVED,
            },
            default=ApprovalOutcome.REJECTED,
        ),
    ),
    blocked_path.SCENARIO_ID: (
        blocked_path.run,
        ScriptedApprovalPolicy(responses={}, default=ApprovalOutcome.REJECTED),
    ),
    conditional_path.SCENARIO_ID: (
        conditional_path.run,
        ScriptedApprovalPolicy(responses={}, default=ApprovalOutcome.REJECTED),
    ),
}


def run_scenario(scenario_id: str, *, out_dir: Path, seed: int = 42) -> ScenarioResult:
    if scenario_id not in SCENARIO_BUILDERS:
        raise KeyError(f"unknown scenario: {scenario_id}")
    runner, approval_policy = SCENARIO_BUILDERS[scenario_id]
    out_dir.mkdir(parents=True, exist_ok=True)
    store = TraceStore(out_dir)
    engine = build_engine(store, approval_resolver=approval_policy.resolve)
    transport = build_transport(store, scenario_id=scenario_id)
    runner(engine, store, transport, seed)
    return ScenarioResult(
        scenario_id=scenario_id,
        trace_path=out_dir / f"{scenario_id}.jsonl",
        events=[e.model_dump(mode="json") for e in store.events_for(scenario_id)],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIO_BUILDERS.keys()))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--out", default="examples/traces")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out_dir = Path(args.out)
    targets = sorted(SCENARIO_BUILDERS.keys()) if args.all else [args.scenario] if args.scenario else []
    if not targets:
        parser.error("specify --scenario or --all")

    for sid in targets:
        path = out_dir / f"{sid}.jsonl"
        if path.exists():
            path.unlink()
        result = run_scenario(sid, out_dir=out_dir, seed=args.seed)
        print(f"[ok] {sid}: {len(result.events)} events → {result.trace_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
