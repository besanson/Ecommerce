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
from gacct.agents.subscription_service import SubscriptionServiceAgent
from gacct.domain.actions import ProposedAction
from gacct.domain.approvals import ApprovalOutcome
from gacct.domain.consumer import ConsumerProfile, ShoppingDelegation
from gacct.domain.context import ConsumerContext
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
        consumer_id="consumer:oli",
        display_name="Oli",
        shipping_country="DE",
        payment_token_id="ptok_demo_001",
        permitted_data_fields=["shipping_address", "payment_token_id"],
    )


def build_consumer_delegation() -> ShoppingDelegation:
    # Used by tests and the UI's static "default" view. Mirrors the canonical
    # mission text above.
    return ShoppingDelegation(
        delegation_id="delegation:half-marathon-shoes",
        consumer_id="consumer:oli",
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


# ---------------------------------------------------------------------------
# Subscription-domain fixtures
# ---------------------------------------------------------------------------

SUBSCRIPTION_MISSION_TEXT = (
    "Renew my active subscriptions up to 15 EUR/month automatically; escalate "
    "renewals between 15-30 EUR; block anything above 30 EUR or any new "
    "service I have not pre-approved. No sharing of payment data beyond token "
    "and billing email. Cancel if the renewal silently changes billing period."
)


def build_subscription_context(*, with_approved_services_version: bool = True) -> ConsumerContext:
    """Oli's data foundation for the subscription mission.

    The data_baseline carries the agent's last-known facts about each real
    service in Oli's portfolio. Spotify's price has drifted by ~10% (still
    within tolerance), DAZN has jumped past the block ceiling, Amazon Prime
    has silently switched from monthly to annual billing, Apple TV+ is new
    and not on the approved list, and BundleSavvy is a billing aggregator
    asking for fields outside the whitelist. These deliberate mismatches
    are what the governance moments exercise.
    """

    delegation_parameters = {
        "monthly_escalate_threshold": 15.0,
        "monthly_block_threshold": 30.0,
        "approved_services": [
            "netflix",
            "spotify",
            "dazn",
            "amazon_prime",
            "disney_plus",
        ],
        "blocked_services": [],
        "billing_data_whitelist": ["payment_token", "billing_email"],
    }
    if with_approved_services_version:
        delegation_parameters["approved_services_version"] = 7
    data_baseline = {
        "subscriptions": {
            "netflix":      {"monthly_eur": 13.99, "billing_period": "monthly", "fresh": True},
            "spotify":      {"monthly_eur":  9.99, "billing_period": "monthly", "fresh": True},
            "dazn":         {"monthly_eur": 19.99, "billing_period": "monthly", "fresh": True},
            "amazon_prime": {"monthly_eur":  8.99, "billing_period": "monthly", "fresh": True},
            "disney_plus":  {"monthly_eur":  8.99, "billing_period": "monthly", "fresh": True},
        },
    }
    return ConsumerContext(
        context_id="ctx:oli-subs",
        context_version=7,
        consumer_id="consumer:oli",
        mission_id="mission:subscription_renewal",
        delegation_parameters=delegation_parameters,
        data_baseline=data_baseline,
    )


def build_subscription_delegation() -> ShoppingDelegation:
    """A ShoppingDelegation built to satisfy the consumer-agent's expectations.

    The subscription scenario does not exercise shopping authority, but the
    ConsumerAgent dataclass still expects a ShoppingDelegation for its
    delegation_id / consumer_id / acting_on_behalf_of plumbing.
    """

    return ShoppingDelegation(
        delegation_id="delegation:subscription-renewal",
        consumer_id="consumer:oli",
        mission=SUBSCRIPTION_MISSION_TEXT,
        budget_ceiling_eur=30.0,            # mirrors monthly_block_threshold
        auto_buy_threshold_eur=15.0,        # mirrors monthly_escalate_threshold
        approved_retailers=[],
        denied_retailers=[],
        forbidden_materials=[],
        substitution_tolerance_pct=0.10,
        delivery_deadline_days=0,
        min_return_window_days=0,
        permitted_data_fields=["payment_token", "billing_email"],
        notes="Subscription-domain delegation; shopping fields are placeholders.",
    )


def build_subscription_services(*, seed=None) -> Dict[str, SubscriptionServiceAgent]:
    """Oli's real-world subscription portfolio with the services' current terms.

    Compare each service's `monthly_eur` against the baseline above to see
    where Oli's data has drifted from reality. These mismatches are the
    governance moments the scenario exercises:

      - netflix:       matches baseline                                → ALLOW
      - spotify:       +10% drift (9.99 → 10.99), within tolerance     → ALLOW_WITH_CONDITIONS
      - dazn:          jumped to 34.99, over the 30 EUR block ceiling  → BLOCK
      - apple_tv:      new service, not on the approved list           → ESCALATE
      - bundle_savvy:  aggregator asking for full card number          → BLOCK
      - amazon_prime:  silently switched from monthly to annual        → ESCALATE
      - disney_plus:   used in the incomplete-context moment           → BLOCK_MISSING_CONTEXT
    """

    return {
        "netflix": SubscriptionServiceAgent(
            service_id="netflix", display_name="Netflix",
            monthly_eur=13.99, billing_period="monthly",
        ),
        "spotify": SubscriptionServiceAgent(
            service_id="spotify", display_name="Spotify Premium",
            monthly_eur=10.49, billing_period="monthly",  # +5% drift, inside 10% tolerance
        ),
        "dazn": SubscriptionServiceAgent(
            service_id="dazn", display_name="DAZN Total",
            monthly_eur=34.99, billing_period="monthly",  # jumped past 30 EUR ceiling
        ),
        "apple_tv": SubscriptionServiceAgent(
            service_id="apple_tv", display_name="Apple TV+",
            monthly_eur=9.99, billing_period="monthly",   # not on approved list
        ),
        "bundle_savvy": SubscriptionServiceAgent(
            service_id="bundle_savvy", display_name="BundleSavvy (aggregator)",
            monthly_eur=5.0, billing_period="monthly",
            requires_data_fields=["full_card_number", "billing_email"],
        ),
        "amazon_prime": SubscriptionServiceAgent(
            service_id="amazon_prime", display_name="Amazon Prime",
            monthly_eur=8.99, billing_period="annual",    # silent period change
        ),
        "disney_plus": SubscriptionServiceAgent(
            service_id="disney_plus", display_name="Disney+",
            monthly_eur=8.99, billing_period="monthly",
        ),
    }


def build_transport(
    trace_store: TraceStore, scenario_id: str
) -> MCPTransport:
    """A transport that streams every MCP message into the trace store under
    the given scenario_id."""

    return MCPTransport(
        on_message=lambda msg: trace_store.record_mcp(scenario_id=scenario_id, message=msg)
    )
