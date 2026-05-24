"""Bypass-resistance tests.

These tests assert structural properties about the package: that side-effect
APIs do not exist outside the governance path, that agents cannot import a
'force_execute' helper, and that the engine has no public escape hatch.
"""

from __future__ import annotations

import inspect

from gacct.agents.consumer_agent import ConsumerAgent
from gacct.agents.retailer_agent import RetailerAgent
from gacct.governance import engine as engine_module


def test_engine_has_no_force_execute_attribute():
    assert not hasattr(engine_module.GovernanceEngine, "force_execute")
    assert not hasattr(engine_module.GovernanceEngine, "skip_governance")
    assert not hasattr(engine_module.GovernanceEngine, "bypass")


def test_consumer_agent_does_not_import_retailer_confirm_order():
    """The consumer agent must never call retailer.confirm_order directly.

    It may pass a confirm_order *callable* into engine.govern as a side_effect,
    but only the engine decides whether that callable runs.
    """

    src = inspect.getsource(ConsumerAgent)
    # The only acceptable reference is via the engine's side_effect parameter.
    direct_calls = [
        line for line in src.splitlines()
        if "retailer.confirm_order(" in line and "side_effect" not in line and "lambda" not in line
    ]
    assert direct_calls == [], (
        "consumer agent appears to call retailer.confirm_order outside the engine: "
        f"{direct_calls}"
    )


def test_retailer_agent_does_not_import_governance():
    """The retailer agent must not import or depend on the governance package.

    The retailer-side surface is supposed to be governance-agnostic; the
    enforcement boundary lives on the consumer side."""

    src = inspect.getsource(RetailerAgent)
    import_lines = [
        ln.strip() for ln in src.splitlines()
        if ln.strip().startswith(("from ", "import "))
    ]
    bad = [ln for ln in import_lines if "gacct.governance" in ln]
    assert not bad, f"retailer agent imports governance: {bad}"


def test_engine_govern_is_only_public_action_path():
    """The engine class exposes exactly one public method for governed action:
    `govern`. Any other public callable that takes a ProposedAction would be a
    smell."""

    public = [
        name for name in dir(engine_module.GovernanceEngine)
        if not name.startswith("_")
    ]
    # Allowed public members.
    assert "govern" in public
    suspicious = [n for n in public if n not in {"govern"}]
    # Properties/dataclass-style accessors etc. are fine - but no method should
    # be named like a side-effect runner.
    for n in suspicious:
        assert not any(token in n.lower() for token in ("execute", "run", "apply", "commit"))
