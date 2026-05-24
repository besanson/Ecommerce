from __future__ import annotations

from gacct.intent.parser import parse_consumer_intent


def test_extracts_canonical_mission():
    text = (
        "Buy running shoes for a half marathon within 180 EUR, from approved retailers "
        "only, no leather products, delivery within 3 days, substitution only within 10 "
        "percent price variance, no auto-purchase above 150 EUR, and no sharing of "
        "personal data beyond shipping details and payment token."
    )
    parsed = parse_consumer_intent(text)
    d = parsed.delegation
    assert d.budget_ceiling_eur == 180.0
    assert d.auto_buy_threshold_eur == 150.0
    assert d.delivery_deadline_days == 3
    assert d.substitution_tolerance_pct == 0.10
    assert "leather" in d.forbidden_materials
    assert "retailer:shady_kicks" in d.denied_retailers
    assert "shipping_address" in d.permitted_data_fields
    assert "payment_token_id" in d.permitted_data_fields


def test_falls_back_to_defaults_when_blank():
    parsed = parse_consumer_intent("buy shoes")
    d = parsed.delegation
    assert d.budget_ceiling_eur == 180.0  # default
    assert d.delivery_deadline_days == 7  # default
    assert d.min_return_window_days == 14  # default
    assert d.forbidden_materials == []
    assert parsed.parsing_trace, "parsing trace should not be empty"


def test_parsing_trace_explains_every_field():
    parsed = parse_consumer_intent("buy shoes within 200 EUR no leather")
    joined = " | ".join(parsed.parsing_trace)
    assert "Budget" in joined
    assert "Auto-buy" in joined
    assert "Delivery" in joined
    assert "Forbidden materials" in joined
