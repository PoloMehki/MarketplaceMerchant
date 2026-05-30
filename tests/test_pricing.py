"""Task 5.1: pricing tests — below-median skew, budget cap, ordering invariants."""
import pytest

from negagent.models import Comp, PriceTargets, TargetSpec
from negagent.pipeline.pricing import compute_targets

# comps with asking prices: 400, 420, 380, 440, 360 → median=400, mean=400
COMPS = [
    Comp(source="amazon", title="iPhone 13", price=400.0, condition="used", url="u1"),
    Comp(source="ebay",   title="iPhone 13", price=420.0, condition="used", url="u2"),
    Comp(source="ebay",   title="iPhone 13", price=380.0, condition="used", url="u3"),
    Comp(source="bestbuy",title="iPhone 13", price=440.0, condition="used", url="u4"),
    Comp(source="target", title="iPhone 13", price=360.0, condition="used", url="u5"),
]

BASE_SPEC = TargetSpec(
    query="iphone 13",
    category="electronics",
    acceptable_conditions=["good"],
    price_mode="below_median_pct",
    threshold_value=0.15,   # 15 % below median
    time_window_minutes=120,
)


def test_targets_below_active_median():
    """good_price must be strictly below the active-listing median."""
    result = compute_targets(COMPS, BASE_SPEC)

    median = 400.0
    assert result.good_price < median


def test_below_median_pct_mode():
    """below_median_pct: target = median * (1 - pct); good_price also below median."""
    result = compute_targets(COMPS, BASE_SPEC)

    expected_target = 400.0 * (1 - 0.15)  # 340.0
    assert result.target == pytest.approx(expected_target)
    assert result.good_price < 400.0


def test_below_avg_pct_mode():
    """below_avg_pct: target = mean * (1 - pct)."""
    spec = BASE_SPEC.model_copy(update={"price_mode": "below_avg_pct"})
    result = compute_targets(COMPS, spec)

    expected_target = 400.0 * (1 - 0.15)  # mean also 400 for this set
    assert result.target == pytest.approx(expected_target)


def test_budget_mode_caps_at_threshold():
    """budget: target = min(threshold_value, good_price); walkaway = threshold."""
    spec = BASE_SPEC.model_copy(update={"price_mode": "budget", "threshold_value": 300.0})
    result = compute_targets(COMPS, spec)

    assert result.walkaway == 300.0
    assert result.target <= 300.0


def test_ordering_invariants():
    """anchor <= target <= walkaway must always hold."""
    for mode in ("below_median_pct", "below_avg_pct", "budget"):
        spec = BASE_SPEC.model_copy(update={"price_mode": mode})
        result = compute_targets(COMPS, spec)
        assert result.anchor <= result.target, f"{mode}: anchor > target"
        assert result.target <= result.walkaway, f"{mode}: target > walkaway"


def test_anchor_below_target():
    """anchor opens below target to leave negotiating room."""
    result = compute_targets(COMPS, BASE_SPEC)
    assert result.anchor < result.target
