"""Task 6.1: test_prompt_contains_rails, test_validate_offer_rejects_above_walkaway.

(The 6.3 gate tests will be added with the approval_gate in the next task.)
Inputs are duck-typed stand-ins for PriceTargets / Listing / Comp.
"""
from types import SimpleNamespace

from negagent.agent.rails import (
    Rails,
    build_rails,
    build_system_prompt,
    default_max_concession,
    validate_concession,
    validate_offer,
)


def _targets(good=80, anchor=70, target=90, walkaway=110):
    return SimpleNamespace(
        good_price=good, anchor=anchor, target=target, walkaway=walkaway
    )


def _listing():
    return SimpleNamespace(
        title="iPhone 12 128GB",
        price=150,
        stated_condition="good",
        url="https://facebook.com/marketplace/item/123",
    )


def _comps():
    return [
        SimpleNamespace(title="iPhone 12 128GB", price=160, condition="good",
                        source="ebay", matched=True, match_confidence=0.92),
        SimpleNamespace(title="iPhone 12 128GB unlocked", price=145, condition="good",
                        source="swappa", matched=True, match_confidence=0.88),
        SimpleNamespace(title="iPhone 11", price=110, condition="fair",
                        source="ebay", matched=False, match_confidence=0.3),
    ]


def test_prompt_contains_rails():
    prompt = build_system_prompt(
        _targets(), _listing(), _comps(), max_concession_per_turn=8
    )

    # All five rails present and explicit.
    assert "walk-away ceiling of $110" in prompt        # Rail 1
    assert "Never disclose" in prompt                    # Rail 2
    assert "no more than $8" in prompt                   # Rail 3
    assert "settle target of $90" in prompt              # Rail 4
    assert "present the best price" in prompt            # Rail 4
    assert "courteous" in prompt.lower()                 # Rail 5

    # Item + comp evidence surfaced; unmatched comp excluded from cited evidence.
    assert "iPhone 12 128GB" in prompt
    assert "$160" in prompt
    assert "iPhone 11" not in prompt


def test_validate_offer_rejects_above_walkaway():
    assert validate_offer(90, 100) is True        # below ceiling
    assert validate_offer(100, 100) is True        # exactly at ceiling allowed
    assert validate_offer(100.01, 100) is False    # above ceiling rejected
    assert validate_offer(150, 100) is False


def test_validate_concession_caps_step():
    assert validate_concession(70, 78, 10) is True    # +8 within cap
    assert validate_concession(70, 80, 10) is True    # +10 exactly at cap
    assert validate_concession(70, 85, 10) is False   # +15 exceeds cap
    assert validate_concession(80, 75, 10) is True    # lowering is fine


def test_default_max_concession_from_targets():
    # room = walkaway(110) - anchor(70) = 40; 20% = 8.0
    assert default_max_concession(_targets()) == 8.0
    # degenerate room floors at 1.0
    assert default_max_concession(_targets(anchor=110, walkaway=110)) == 1.0


def test_build_rails_bundles_prompt_and_guardrails():
    rails = build_rails(_targets(), _listing(), _comps())
    assert isinstance(rails, Rails)
    assert "HARD RAILS" in rails.system_prompt
    assert rails.walkaway == 110
    assert rails.validate_offer(110) is True
    assert rails.validate_offer(111) is False
    # default cap derived from targets (20% of 40 = 8.0)
    assert rails.max_concession_per_turn == 8.0
    assert rails.validate_concession(70, 90) is False   # +20 exceeds cap
