"""verify_stage5_pricing.py — manual: print price targets for a sample comp set.

No external calls — pure logic. Safe to run any time.

Usage:
    python scripts/verify_stage5_pricing.py
"""
import sys

from negagent.models import Comp, TargetSpec
from negagent.pipeline.pricing import compute_targets

# Realistic iPhone 13 comps scraped from the live Apify run
COMPS = [
    Comp(source="amazon", title="Apple iPhone 13 128GB (Renewed)", price=429.99, condition="renewed", url="u1"),
    Comp(source="amazon", title="Apple iPhone 13 256GB (Renewed)", price=499.99, condition="renewed", url="u2"),
    Comp(source="ebay",   title="Apple iPhone 13 128GB Unlocked",  price=389.00, condition="used",    url="u3"),
    Comp(source="ebay",   title="Apple iPhone 13 256GB Unlocked",  price=449.00, condition="used",    url="u4"),
    Comp(source="bestbuy",title="Apple iPhone 13 128GB Pre-Owned", price=459.99, condition="excellent", url="u5"),
]

MODES = [
    ("below_median_pct", 0.15),
    ("below_avg_pct",    0.15),
    ("budget",           350.00),
]


def main() -> int:
    prices = sorted(c.price for c in COMPS)
    print(f"Comps ({len(COMPS)}): {prices}")
    print()
    for mode, threshold in MODES:
        spec = TargetSpec(
            query="iphone 13",
            category="electronics",
            acceptable_conditions=["good", "renewed", "used"],
            price_mode=mode,
            threshold_value=threshold,
            time_window_minutes=120,
        )
        t = compute_targets(COMPS, spec)
        print(f"mode={mode} threshold={threshold}")
        print(f"  good_price=${t.good_price:.2f}  anchor=${t.anchor:.2f}  target=${t.target:.2f}  walkaway=${t.walkaway:.2f}")
        assert t.anchor <= t.target <= t.walkaway, "ordering invariant violated!"
        print()
    print("All ordering invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
