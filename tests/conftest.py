from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from gacct.domain.policies import PolicyPack
from gacct.policy.loader import load_policy_packs
from gacct.scenarios.fixtures import build_consumer_delegation, build_retailers

POLICIES_DIR = Path(__file__).resolve().parents[1] / "policies"


@pytest.fixture(scope="session")
def policy_packs() -> Dict[str, PolicyPack]:
    return load_policy_packs(POLICIES_DIR)


@pytest.fixture
def delegation():
    return build_consumer_delegation()


@pytest.fixture
def retailers():
    return build_retailers()
