"""pricing.py — Task 5.1: compute price targets from active e-commerce comps.

Active-listing skew rule: comps are asking prices and skew high. good_price MUST
sit below the active median/average across ALL modes — not at it.

Ordering invariant enforced: anchor <= target <= walkaway.
"""
from __future__ import annotations

import statistics
from typing import Optional

from negagent.models import Comp, PriceTargets, TargetSpec

# anchor opens this fraction below target to leave negotiating room
_ANCHOR_DISCOUNT = 0.10
# good_price sits this fraction below the median/mean regardless of mode
_SKEW_DISCOUNT = 0.05
# anchor must be at least this far below the listing price when comps skew high
_MIN_LISTING_DISCOUNT = 0.20


def compute_targets(
    comps: list[Comp], spec: TargetSpec, listing_price: Optional[float] = None
) -> PriceTargets:
    """Derive the four negotiation numbers from active comp prices."""
    if not comps:
        if not listing_price:
            raise ValueError("Cannot compute price targets: no comps and no listing price.")
        # No comps — price purely off the listing ask with conservative discounts
        median = listing_price
        mean = listing_price
    else:
        prices = [c.price for c in comps]
        median = statistics.median(prices)
        mean = statistics.mean(prices)

    # good_price: always below the active median (skew rule)
    good_price = median * (1 - _SKEW_DISCOUNT)

    if spec.price_mode == "below_median_pct":
        target = median * (1 - spec.threshold_value)
        walkaway = median  # soft ceiling — median is the market asking price
    elif spec.price_mode == "below_avg_pct":
        target = mean * (1 - spec.threshold_value)
        walkaway = mean
    elif spec.price_mode == "budget":
        target = min(spec.threshold_value, good_price)
        walkaway = spec.threshold_value
    else:
        raise ValueError(f"Unknown price_mode: {spec.price_mode!r}")

    anchor = target * (1 - _ANCHOR_DISCOUNT)

    # when eBay comps skew high vs the FB listing, the comps-based anchor can
    # land too close to the asking price — floor it at a real discount off the
    # listing price so the opening offer is always meaningfully aggressive
    if listing_price is not None and listing_price > 0:
        anchor = min(anchor, listing_price * (1 - _MIN_LISTING_DISCOUNT))

    # enforce ordering invariants
    anchor = min(anchor, target)
    target = min(target, walkaway)

    return PriceTargets(
        good_price=round(good_price, 2),
        anchor=round(anchor, 2),
        target=round(target, 2),
        walkaway=round(walkaway, 2),
    )
