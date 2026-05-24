"""Natural-language consumer intent → structured ShoppingDelegation.

This parser is intentionally a small set of regexes plus keyword lookups —
not an LLM call. The repo runs without API keys. The parser's job here is
demonstrative: it shows how a free-text mission would land as a structured
delegation, and it surfaces a `parsing_trace` so the consumer can audit what
the system inferred from their words. In production this layer would be an
LLM with the same output contract.
"""

from __future__ import annotations

import re
import uuid
from typing import List, Optional

from pydantic import BaseModel

from gacct.domain.consumer import ShoppingDelegation


class ParsedIntent(BaseModel):
    delegation: ShoppingDelegation
    parsing_trace: List[str]


# A small, demo-grade vocabulary. Real deployments would use NER + an LLM.
_RETAILER_ALIASES = {
    "run co": "retailer:run_co",
    "run-co": "retailer:run_co",
    "runco": "retailer:run_co",
    "trail works": "retailer:trail_works",
    "trailworks": "retailer:trail_works",
    "shady kicks": "retailer:shady_kicks",
}
_KNOWN_RETAILERS = set(_RETAILER_ALIASES.values())

_FORBIDDEN_MATERIALS_VOCAB = {"leather", "fur", "suede", "wool"}

_DATA_FIELDS_VOCAB = {
    "shipping": "shipping_address",
    "shipping address": "shipping_address",
    "address": "shipping_address",
    "payment": "payment_token_id",
    "payment token": "payment_token_id",
    "phone": "phone_number",
    "phone number": "phone_number",
    "email": "email_address",
    "marketing": "marketing_consent",
}


def parse_consumer_intent(
    text: str,
    *,
    consumer_id: str = "consumer:eva",
    delegation_id: Optional[str] = None,
    default_approved_retailers: Optional[List[str]] = None,
) -> ParsedIntent:
    """Extract a delegation from free-text intent.

    The parsing is best-effort and explicitly traced. Anything the parser
    cannot infer falls back to conservative defaults (low budget, no
    forbidden materials, strict whitelist).
    """

    trace: List[str] = []
    lower = text.lower()

    # --- mission summary ---
    mission_summary = text.strip()
    if len(mission_summary) > 240:
        mission_summary = mission_summary[:237] + "…"

    # --- budget ceiling ---
    budget = 180.0
    m = re.search(r"(?:within|under|up\s*to|max(?:imum)?)\s*(?:€|EUR\s*)?(\d{2,5})\s*(?:eur|€|euros?)?", lower)
    if m:
        budget = float(m.group(1))
        trace.append(f"Budget ceiling €{budget:.0f} — matched on '{m.group(0)}'.")
    else:
        trace.append(f"Budget ceiling €{budget:.0f} — default (no explicit phrase found).")

    # --- auto-buy threshold ---
    threshold = round(budget * 0.83)
    m = re.search(r"(?:no\s+auto[-\s]?(?:purchase|buy)|auto[-\s]?(?:purchase|buy)\s+threshold)\s*(?:above|over|>)?\s*(?:€|EUR\s*)?(\d{2,5})", lower)
    if m:
        threshold = float(m.group(1))
        trace.append(f"Auto-buy threshold €{threshold:.0f} — matched on '{m.group(0)}'.")
    else:
        trace.append(
            f"Auto-buy threshold €{threshold:.0f} — derived as ≈83% of budget (no explicit phrase)."
        )

    # --- delivery deadline ---
    delivery_days = 7
    m = re.search(r"(?:within|in|delivery\s+within|deliver(?:y)?\s+in)\s+(\d{1,3})\s*(?:day|days|d)", lower)
    if m:
        delivery_days = int(m.group(1))
        trace.append(f"Delivery deadline {delivery_days}d — matched on '{m.group(0)}'.")
    else:
        trace.append(f"Delivery deadline {delivery_days}d — default.")

    # --- return window minimum ---
    return_days = 14
    m = re.search(r"return(?:s)?\s+(?:window|policy|of|min(?:imum)?)?\s*(?:of|at\s+least)?\s*(\d{1,3})\s*(?:day|days|d)", lower)
    if m:
        return_days = int(m.group(1))
        trace.append(f"Minimum return window {return_days}d — matched on '{m.group(0)}'.")
    else:
        trace.append(f"Minimum return window {return_days}d — default.")

    # --- substitution tolerance ---
    sub_tol = 0.10
    m = re.search(r"substitut(?:ion|e)[^.,;]*?(\d{1,2})\s*(?:%|percent|pct)", lower)
    if m:
        sub_tol = int(m.group(1)) / 100.0
        trace.append(f"Substitution tolerance {sub_tol:.0%} — matched on '{m.group(0)}'.")
    else:
        trace.append(f"Substitution tolerance {sub_tol:.0%} — default.")

    # --- forbidden materials ---
    forbidden: List[str] = []
    for vocab in _FORBIDDEN_MATERIALS_VOCAB:
        if re.search(rf"\bno\s+{vocab}\b|\bnon[-\s]?{vocab}\b|\bavoid\s+{vocab}\b", lower):
            forbidden.append(vocab)
    if forbidden:
        trace.append(f"Forbidden materials: {forbidden}.")
    else:
        trace.append("Forbidden materials: none mentioned.")

    # --- approved retailers ---
    approved = list(default_approved_retailers or [])
    for alias, retailer_id in _RETAILER_ALIASES.items():
        if alias in lower and retailer_id not in approved:
            approved.append(retailer_id)
    if not approved:
        approved = ["retailer:run_co", "retailer:trail_works"]
        trace.append(
            "Approved retailers: defaulted to ['retailer:run_co', 'retailer:trail_works'] "
            "(no explicit list found)."
        )
    else:
        trace.append(f"Approved retailers: {approved}.")

    # --- denied retailers (explicit "not"/"avoid") ---
    denied: List[str] = []
    for alias, retailer_id in _RETAILER_ALIASES.items():
        if re.search(rf"\b(?:not|avoid|never|exclude)\s+{re.escape(alias)}\b", lower):
            denied.append(retailer_id)
    # If the consumer mentions "approved retailers only" we conservatively deny shady kicks.
    if "approved retailers only" in lower and "retailer:shady_kicks" not in denied and "retailer:shady_kicks" not in approved:
        denied.append("retailer:shady_kicks")
        trace.append(
            "Denied retailers: defaulted to ['retailer:shady_kicks'] because 'approved retailers only' "
            "implies others are not allowed."
        )
    elif denied:
        trace.append(f"Denied retailers: {denied}.")
    else:
        trace.append("Denied retailers: none.")

    # --- permitted data fields ---
    permitted = ["shipping_address", "payment_token_id"]
    if "no sharing" in lower or "no personal data" in lower:
        trace.append("Data sharing: limited to shipping_address and payment_token_id (default whitelist).")
    else:
        trace.append("Data sharing: whitelisted shipping_address and payment_token_id (default).")

    delegation = ShoppingDelegation(
        delegation_id=delegation_id or f"delegation:{uuid.uuid4().hex[:8]}",
        consumer_id=consumer_id,
        mission=mission_summary,
        budget_ceiling_eur=budget,
        auto_buy_threshold_eur=threshold,
        approved_retailers=approved,
        denied_retailers=denied,
        forbidden_materials=forbidden,
        substitution_tolerance_pct=sub_tol,
        delivery_deadline_days=delivery_days,
        min_return_window_days=return_days,
        permitted_data_fields=permitted,
        notes=f"Parsed from consumer free-text on {uuid.uuid4().hex[:6]}.",
    )
    return ParsedIntent(delegation=delegation, parsing_trace=trace)
