"""Tasks 6.1 + 6.3: prompt rails, numeric guardrails, and HITL approval gate.

Inputs are duck-typed stand-ins for PriceTargets / Listing / Comp.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from negagent.agent.rails import (
    SEND_TOOLS,
    HITLApprovalGate,
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


# --- Task 6.3: HITLApprovalGate ---

def _mock_event(tool_name: str, tool_input: dict | None = None) -> MagicMock:
    """Build a mock BeforeToolCallEvent with controlled tool_use."""
    event = MagicMock()
    event.tool_use = {"name": tool_name, "input": tool_input or {}}
    event.cancel_tool = False
    return event


def test_gate_blocks_send_without_approval():
    gate = HITLApprovalGate(approval_fn=lambda name, inp: False)
    for send_tool in SEND_TOOLS:
        event = _mock_event(send_tool, {"text": "Would you take $90?"})
        gate._check_send(event)
        assert event.cancel_tool != False, f"Expected cancel_tool set for {send_tool!r}"


def test_gate_allows_read_tools():
    # approval_fn always denies — but it must never be called for read tools
    called = []
    def deny_and_track(name, inp):
        called.append(name)
        return False

    gate = HITLApprovalGate(approval_fn=deny_and_track)
    read_tools = [
        "browser_navigate", "browser_snapshot", "browser_take_screenshot",
        "browser_click", "browser_wait_for", "browser_navigate_back",
        "browser_console_messages", "browser_tabs",
    ]
    for tool in read_tools:
        event = _mock_event(tool)
        gate._check_send(event)
        assert event.cancel_tool is False, f"cancel_tool wrongly set for read tool {tool!r}"

    assert called == [], "approval_fn should never be called for read-only tools"


def test_gate_allows_send_on_approve():
    gate = HITLApprovalGate(approval_fn=lambda name, inp: True)
    for send_tool in SEND_TOOLS:
        event = _mock_event(send_tool, {"text": "Would you take $90?"})
        gate._check_send(event)
        assert event.cancel_tool is False, f"cancel_tool wrongly set on approval for {send_tool!r}"
