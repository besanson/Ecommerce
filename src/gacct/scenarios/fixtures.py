"""Static fixtures the scripted scenarios share.

Wires together: the policy engine, the MCP transport, the retailer catalogue,
the trace store, and the consumer-side reasoner. The same trace store
receives decision records (from PAA), agent thoughts (from the reasoner),
and MCP messages (from the transport), so a single sequenced timeline
captures every reasoning step, every wire message, and every governed
action.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

from gacct.agents.retailer_agent import RetailerAgent
from gacct.domain.actions import ProposedAction
from gacct.domain.approvals import ApprovalOutcome
from gacct.domain.consumer import ConsumerProfile, ShoppingDelegation
from gacct.domain.product import ProductOffer, RetailerTerms
from gacct.governance.engine import GovernanceEngine
from gacct.governance.pag import PAGOutcome
from gacct.mcp.transport import MCPTransport
from gacct.policy.loader import load_policy_packs
from gacct.trace.store import TraceStore

POLICIES_DIR = Path(__file__).resolve().parents[3] / "policies"


# ---------------------------------------------------------------------------
# Canonical mission texts, used both as fixture inputs and as on-screen prompts
# ---------------------------------------------------------------------------

DEFAULT_MISSION_TEXT = (
    "Buy running shoes for a half marathon within 180 EUR, from approved retailers "
    "only, no leather products, delivery within 3 days, substitution only within 10 "
    "percent price variance, no auto-purchase above 150 EUR, and no sharing of "
    "personal data beyond shipping details and payment token."
)


def build_consumer_profile() -> ConsumerProfile:
    return ConsumerProfile(
        consumer_id="consumer:eva",
        display_name="Eva",
        shipping_country="DE",
        payment_token_id="ptok_demo_001",
        permitted_data_fields=["shipping_address", "payment_token_id"],
    )


def build_consumer_delegation() -> ShoppingDelegation:
    # Used by tests and the UI's static "default" view. Mirrors the canonical
    # mission text above.
    return ShoppingDelegation(
        delegation_id="delegation:half-marathon-shoes",
        consumer_id="consumer:eva",
        mission="Buy running shoes for a half marathon",
        budget_ceiling_eur=180.0,
        auto_buy_threshold_eur=150.0,
        approved_retailers=["retailer:run_co", "retailer:trail_works"],
        denied_retailers=["retailer:shady_kicks"],
        forbidden_materials=["leather"],
        substitution_tolerance_pct=0.10,
        delivery_deadline_days=3,
        min_return_window_days=14,
        permitted_data_fields=["shipping_address", "payment_token_id"],
        notes="Half marathon next month; expedited shipping preferred but bounded by total spend.",
    )


def _terms(return_days: int, discount: float = 0.0, requires=None) -> RetailerTerms:
    return RetailerTerms(
        return_window_days=return_days,
        free_returns=True,
        requires_data_fields=requires or ["shipping_address", "payment_token_id"],
        promotion_discount_eur=discount,
    )


def build_retailers(seed: Optional[int] = None) -> Dict[str, RetailerAgent]:
    return {
        "retailer:run_co": RetailerAgent(
            retailer_id="retailer:run_co",
            display_name="Run Co.",
            catalogue=[
                ProductOffer(
                    offer_id="offer:run_co:rc-aero-1",
                    retailer_id="retailer:run_co",
                    sku="RC-AERO-1",
                    title="Aero Lite 1 (mesh)",
                    price_eur=139.0,
                    shipping_eur=6.0,
                    shipping_days=2,
                    materials=["mesh", "rubber", "eva_foam"],
                    in_stock=True,
                    terms=_terms(return_days=30),
                ),
                ProductOffer(
                    offer_id="offer:run_co:rc-aero-2",
                    retailer_id="retailer:run_co",
                    sku="RC-AERO-2",
                    title="Aero Lite 2 (mesh)",
                    price_eur=159.0,
                    shipping_eur=6.0,
                    shipping_days=2,
                    materials=["mesh", "rubber", "eva_foam"],
                    in_stock=True,
                    terms=_terms(return_days=30),
                ),
                ProductOffer(
                    offer_id="offer:run_co:rc-leather-classic",
                    retailer_id="retailer:run_co",
                    sku="RC-LCLASSIC",
                    title="Heritage Trainer (leather)",
                    price_eur=125.0,
                    shipping_eur=6.0,
                    shipping_days=2,
                    materials=["leather", "rubber"],
                    in_stock=True,
                    terms=_terms(return_days=30),
                ),
            ],
            seed=seed,
        ),
        "retailer:trail_works": RetailerAgent(
            retailer_id="retailer:trail_works",
            display_name="Trail Works",
            catalogue=[
                ProductOffer(
                    offer_id="offer:trail_works:tw-fast-3",
                    retailer_id="retailer:trail_works",
                    sku="TW-FAST-3",
                    title="Fast 3 Road Runner",
                    price_eur=149.0,
                    shipping_eur=8.0,
                    shipping_days=4,
                    materials=["mesh", "rubber"],
                    in_stock=True,
                    terms=_terms(return_days=30),
                ),
            ],
            # Trail Works asks for more than the consumer's whitelist.
            requires_data_fields=[
                "shipping_address",
                "payment_token_id",
                "phone_number",
                "marketing_consent",
            ],
            seed=seed,
        ),
        "retailer:shady_kicks": RetailerAgent(
            retailer_id="retailer:shady_kicks",
            display_name="Shady Kicks",
            catalogue=[
                ProductOffer(
                    offer_id="offer:shady_kicks:sk-cheap-1",
                    retailer_id="retailer:shady_kicks",
                    sku="SK-CHEAP-1",
                    title="Generic Runner",
                    price_eur=49.0,
                    shipping_eur=5.0,
                    shipping_days=10,
                    materials=["mesh", "rubber"],
                    in_stock=True,
                    terms=_terms(return_days=3),
                ),
            ],
            seed=seed,
        ),
    }


def build_engine(
    trace_store: TraceStore,
    approval_resolver: Optional[Callable[[ProposedAction, PAGOutcome], ApprovalOutcome]] = None,
) -> GovernanceEngine:
    packs = load_policy_packs(POLICIES_DIR)
    return GovernanceEngine(
        packs,
        on_record=trace_store.record_decision,
        approval_resolver=approval_resolver,
    )


def build_transport(
    trace_store: TraceStore, scenario_id: str
) -> MCPTransport:
    """A transport that streams every MCP message into the trace store under
    the given scenario_id."""

    return MCPTransport(
        on_message=lambda msg: trace_store.record_mcp(scenario_id=scenario_id, message=msg)
    )
