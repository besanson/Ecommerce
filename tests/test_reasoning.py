from __future__ import annotations

from gacct.domain.product import ProductOffer, RetailerTerms
from gacct.reasoning.engine import ConsumerAgentReasoner


def _offer(sku: str, price: float, materials, in_stock: bool = True) -> ProductOffer:
    return ProductOffer(
        offer_id=f"o:{sku}",
        retailer_id="retailer:test",
        sku=sku,
        title=sku,
        price_eur=price,
        shipping_eur=5.0,
        shipping_days=2,
        materials=list(materials),
        in_stock=in_stock,
        terms=RetailerTerms(return_window_days=30, free_returns=True),
    )


def test_reasoner_filters_forbidden_materials(delegation):
    r = ConsumerAgentReasoner(delegation, seed=1)
    offers = [
        _offer("ok-1", 100, ["mesh"]),
        _offer("bad-1", 80, ["leather"]),
        _offer("ok-2", 130, ["mesh", "rubber"]),
    ]
    thoughts = r.think_about_offers(offers)
    topics = [t.topic for t in thoughts]
    assert "filter" in topics
    assert any("forbidden" in t.content.lower() for t in thoughts)
    assert any("Top pick" in t.content for t in thoughts)


def test_reasoner_explains_substitute_outside_tolerance(delegation):
    r = ConsumerAgentReasoner(delegation, seed=1)
    original = _offer("orig", 140.0, ["mesh"])
    sub = _offer("sub", 160.0, ["mesh"])  # +14% from 140
    thoughts = r.think_about_substitute(original, sub)
    assert any("ESCALATE" in t.content for t in thoughts), thoughts


def test_reasoner_predicts_block_on_extra_data(delegation):
    r = ConsumerAgentReasoner(delegation, seed=1)
    thoughts = r.think_about_data_request(["shipping_address", "marketing_consent"])
    assert any("BLOCK" in t.content for t in thoughts)
