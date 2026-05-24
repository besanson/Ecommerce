"""Simulated reasoning for the consumer shopping agent.

This is not an LLM. It is a deterministic explanatory layer that, given the
delegation and the facts of the moment, produces the kind of thought trace a
real reasoning agent would emit. The point is to make the agent's intent
visible - to the audience, to the trace store, and to the governance layer's
forensics view.

The reasoning never has authority to act. It informs which `ProposedAction`
the consumer agent constructs, but the action still flows through the
governance engine on its own merits.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Sequence

from gacct.domain.consumer import ShoppingDelegation
from gacct.domain.product import ProductOffer


@dataclass
class Thought:
    """A single line in the agent's reasoning trail."""

    topic: str  # e.g., "mission", "filter", "rank", "substitute", "data_request"
    content: str


class ConsumerAgentReasoner:
    """Emits structured thoughts based on the delegation and the facts at hand."""

    def __init__(self, delegation: ShoppingDelegation, seed: Optional[int] = None):
        self.delegation = delegation
        self._rng = random.Random(seed) if seed is not None else random.Random()

    # -- mission framing ---------------------------------------------------

    def think_about_mission(self) -> List[Thought]:
        d = self.delegation
        return [
            Thought("mission", f"Consumer mission: {d.mission!r}."),
            Thought(
                "constraints",
                f"Hard bounds: budget ≤ €{d.budget_ceiling_eur:.0f}, "
                f"auto-buy ≤ €{d.auto_buy_threshold_eur:.0f}, "
                f"delivery ≤ {d.delivery_deadline_days}d, "
                f"return window ≥ {d.min_return_window_days}d.",
            ),
            Thought(
                "preferences",
                f"Substitution tolerance {d.substitution_tolerance_pct:.0%}. "
                f"Forbidden materials: {d.forbidden_materials or 'none'}. "
                f"Permitted data fields: {d.permitted_data_fields}.",
            ),
            Thought(
                "retailers",
                f"Approved retailers ({len(d.approved_retailers)}): {d.approved_retailers}. "
                f"Denied: {d.denied_retailers or 'none'}.",
            ),
            Thought(
                "plan",
                "Plan: query an approved retailer for in-stock offers, filter by "
                "material policy, rank by total cost then shipping speed, then "
                "propose the top governed actions in order.",
            ),
        ]

    # -- offer evaluation --------------------------------------------------

    def think_about_offers(self, offers: Sequence[ProductOffer]) -> List[Thought]:
        d = self.delegation
        forbidden = {m.lower() for m in d.forbidden_materials}

        out_of_stock = [o for o in offers if not o.in_stock]
        with_forbidden = [o for o in offers if {m.lower() for m in o.materials} & forbidden]
        feasible = [
            o for o in offers
            if o.in_stock and not ({m.lower() for m in o.materials} & forbidden)
        ]

        thoughts = [
            Thought("ingest", f"Received {len(offers)} candidate offers from the retailer."),
        ]
        if out_of_stock:
            skus = ", ".join(o.sku for o in out_of_stock)
            thoughts.append(Thought("filter", f"Dropping {len(out_of_stock)} out-of-stock: {skus}."))
        if with_forbidden:
            skus = ", ".join(o.sku for o in with_forbidden)
            thoughts.append(
                Thought(
                    "filter",
                    f"Dropping {len(with_forbidden)} containing forbidden materials "
                    f"({sorted(forbidden)}): {skus}.",
                )
            )
        thoughts.append(
            Thought("rank", f"{len(feasible)} feasible offer(s) remain; ranking by total then shipping days.")
        )
        if feasible:
            ranked = sorted(feasible, key=lambda o: (o.total_eur, o.shipping_days))
            top = ranked[0]
            thoughts.append(
                Thought(
                    "select",
                    f"Top pick: {top.title} (sku={top.sku}) at €{top.total_eur:.2f}, "
                    f"ships in {top.shipping_days}d. Will propose select_merchant + place_order.",
                )
            )
        else:
            thoughts.append(
                Thought(
                    "select",
                    "No feasible offer remains; cannot proceed without violating delegation.",
                )
            )
        return thoughts

    # -- substitute proposed by retailer ----------------------------------

    def think_about_substitute(
        self, original: ProductOffer, substitute: ProductOffer
    ) -> List[Thought]:
        d = self.delegation
        if original.price_eur <= 0:
            variance = float("inf")
        else:
            variance = (substitute.price_eur - original.price_eur) / original.price_eur
        in_tol = abs(variance) <= d.substitution_tolerance_pct
        msgs = [
            Thought(
                "substitute",
                f"Retailer proposed substitute {substitute.title} (sku={substitute.sku}) at "
                f"€{substitute.price_eur:.2f}. Original was {original.sku} at €{original.price_eur:.2f}.",
            ),
            Thought(
                "compute",
                f"Price variance {variance:+.1%} vs my substitution tolerance "
                f"{d.substitution_tolerance_pct:.0%}.",
            ),
        ]
        if in_tol:
            msgs.append(
                Thought(
                    "expect",
                    "Within tolerance - expect ALLOW. I will propose accept_substitute.",
                )
            )
        else:
            msgs.append(
                Thought(
                    "expect",
                    "Outside tolerance - substitution pack will ESCALATE; consumer must approve.",
                )
            )
        # Also flag the budget interaction.
        new_total = substitute.total_eur
        if new_total > d.auto_buy_threshold_eur:
            msgs.append(
                Thought(
                    "expect",
                    f"Substitute total €{new_total:.2f} also exceeds auto-buy threshold "
                    f"€{d.auto_buy_threshold_eur:.0f}; expect a second ESCALATE on the order itself.",
                )
            )
        return msgs

    # -- data sharing -----------------------------------------------------

    def think_about_data_request(self, requested_fields: Sequence[str]) -> List[Thought]:
        d = self.delegation
        whitelist = set(d.permitted_data_fields)
        extra = sorted(set(requested_fields) - whitelist)
        msgs = [
            Thought(
                "data",
                f"Retailer requires these fields: {list(requested_fields)}.",
            ),
            Thought(
                "data",
                f"My permitted fields: {sorted(whitelist)}.",
            ),
        ]
        if not extra:
            msgs.append(Thought("expect", "All requested fields are whitelisted; expect ALLOW."))
        else:
            msgs.append(
                Thought(
                    "expect",
                    f"Extra fields outside whitelist: {extra}. data_sharing pack will BLOCK.",
                )
            )
        return msgs

    # -- return terms -----------------------------------------------------

    def think_about_return_terms(self, offer: ProductOffer) -> List[Thought]:
        d = self.delegation
        ok = offer.terms.return_window_days >= d.min_return_window_days
        return [
            Thought(
                "returns",
                f"Retailer offers {offer.terms.return_window_days}-day returns; "
                f"my minimum is {d.min_return_window_days}d.",
            ),
            Thought(
                "expect",
                "Meets minimum; expect ALLOW." if ok else "Below minimum; returns pack will BLOCK.",
            ),
        ]

    # -- merchant selection -----------------------------------------------

    def think_about_merchant(self, retailer_id: str) -> List[Thought]:
        d = self.delegation
        ok = retailer_id in d.approved_retailers and retailer_id not in d.denied_retailers
        if retailer_id in d.denied_retailers:
            verdict = "On the denied list - retailers pack will BLOCK."
        elif retailer_id not in d.approved_retailers:
            verdict = "Not on the approved list - retailers pack will BLOCK."
        else:
            verdict = "Approved and not denied - expect ALLOW."
        return [
            Thought(
                "merchant",
                f"Considering retailer {retailer_id}. Approved={ok}. {verdict}",
            )
        ]
