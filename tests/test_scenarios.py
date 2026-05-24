from __future__ import annotations

from gacct.scenarios.runner import SCENARIO_BUILDERS, run_scenario


def _decisions(result):
    return [e for e in result.events if e["event_type"] == "decision"]


def test_every_scenario_records_acting_on_behalf_of(tmp_path):
    for sid in SCENARIO_BUILDERS:
        result = run_scenario(sid, out_dir=tmp_path / sid)
        for d in _decisions(result):
            assert d["detail"]["acting_on_behalf_of"].startswith("consumer:")
            assert d["detail"]["policies_evaluated"], (
                f"{sid}/{d['detail']['intended_action']}: missing policies_evaluated"
            )
