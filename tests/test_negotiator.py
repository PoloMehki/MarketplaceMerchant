"""Tasks 6.2 + 6.4: agent wiring and reply-loop turn handling.

No real browser or AWS calls are made: Agent and MCPClient are patched for 6.2.
6.4 tests use an in-memory SQLite repo and duck-typed rails stand-ins.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from negagent.agent.negotiator import (
    build_agent,
    build_mcp_client,
    decide_next_action,
    handle_seller_reply,
    parse_seller_reply,
    user_data_dir_from_mcp_config,
)
from negagent.agent.rails import build_rails
from negagent.store.negotiation_repo import NegotiationRepo


def _rails():
    targets = SimpleNamespace(good_price=80, anchor=70, target=90, walkaway=110)
    listing = SimpleNamespace(
        title="iPhone 12 128GB", price=150, stated_condition="good", url="n/a"
    )
    return build_rails(targets, listing, [])


def test_agent_builds_with_mocked_mcp():
    rails = _rails()
    mock_mcp = MagicMock()
    mock_model = MagicMock()

    # Patch Agent in the negotiator module so no Bedrock / MCP connection fires.
    with patch("negagent.agent.negotiator.Agent") as MockAgent:
        MockAgent.return_value = MagicMock()
        agent = build_agent(mock_model, rails, mock_mcp)

        MockAgent.assert_called_once()
        kwargs = MockAgent.call_args.kwargs
        assert kwargs["system_prompt"] == rails.system_prompt
        assert mock_mcp in kwargs["tools"]
        assert kwargs["model"] is mock_model
        # No hooks supplied -> empty list passed.
        assert kwargs["hooks"] == []


def test_agent_builds_with_hooks():
    rails = _rails()
    mock_mcp = MagicMock()
    mock_model = MagicMock()
    sentinel_hook = MagicMock()

    with patch("negagent.agent.negotiator.Agent") as MockAgent:
        MockAgent.return_value = MagicMock()
        build_agent(mock_model, rails, mock_mcp, hooks=[sentinel_hook])

        kwargs = MockAgent.call_args.kwargs
        assert sentinel_hook in kwargs["hooks"]


def test_build_mcp_client_uses_correct_user_data_dir():
    udd = "/test/.fb-profile"

    with patch("negagent.agent.negotiator.MCPClient") as MockMCPClient, \
         patch("negagent.agent.negotiator.stdio_client") as mock_stdio, \
         patch("negagent.agent.negotiator.StdioServerParameters") as MockParams:

        build_mcp_client(udd)

        # MCPClient was constructed with a transport callable.
        MockMCPClient.assert_called_once()
        transport_callable = MockMCPClient.call_args[0][0]

        # Invoke the lambda to trigger the StdioServerParameters construction.
        transport_callable()
        MockParams.assert_called_once_with(
            command="npx",
            args=["@playwright/mcp@latest", "--user-data-dir", udd],
        )


def test_user_data_dir_from_mcp_config(tmp_path):
    cfg = {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": ["@playwright/mcp@latest", "--user-data-dir", "/abs/.fb-profile"],
            }
        }
    }
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    assert user_data_dir_from_mcp_config(p) == "/abs/.fb-profile"


# ---------------------------------------------------------------------------
# Task 6.4 — Reply read loop + turn handling
# ---------------------------------------------------------------------------

_SNAPSHOT_WITH_OFFER = (
    "Conversation with Seller\n"
    "You: Hi, I'm interested in the chair.\n"
    "Seller: It's barely used, best I can do is $480."
)

_SNAPSHOT_NO_PRICE = (
    "Conversation with Seller\n"
    "You: Hi, I'm interested in the chair.\n"
    "Seller: Let me think about it and get back to you."
)


@pytest.fixture
def repo():
    r = NegotiationRepo.open(":memory:")
    r.create("L1")
    yield r
    r.close()


def _simple_rails(target=450.0, walkaway=520.0):
    """Duck-typed rails stand-in for 6.4 tests (no system_prompt needed)."""
    return SimpleNamespace(target=target, walkaway=walkaway)


def test_reply_parsed_and_state_updated(repo):
    action, state = handle_seller_reply(
        _SNAPSHOT_WITH_OFFER, "L1", repo, _simple_rails()
    )

    assert action == "counter"          # 480 > target(450), <= walkaway(520)
    assert state["best_price_found"] == 480.0
    assert len(state["turns"]) == 1
    assert state["turns"][0]["role"] == "seller"
    assert state["turns"][0]["amount"] == 480.0
    assert state["status"] == "active"


def test_walkaway_triggers_when_seller_above_ceiling(repo):
    rails = _simple_rails(target=450, walkaway=500)
    action, state = handle_seller_reply(
        "Seller: How about $510?", "L1", repo, rails
    )
    assert action == "walkaway"
    assert state["status"] == "walked"


def test_accept_when_at_or_below_target(repo):
    rails = _simple_rails(target=450, walkaway=520)
    action, state = handle_seller_reply(
        "Seller: Fine, I'll take $440.", "L1", repo, rails
    )
    assert action == "accept"
    assert state["status"] == "accepted"
    assert state["current_offer"] == 440.0


def test_no_reply_when_snapshot_has_no_price(repo):
    action, state = handle_seller_reply(
        _SNAPSHOT_NO_PRICE, "L1", repo, _simple_rails()
    )

    assert action == "no_reply"
    assert state["turns"] == []
    assert state["best_price_found"] is None


def test_parse_seller_reply_extracts_last_price():
    assert parse_seller_reply("I want $500, but I can do $480.") == 480.0
    assert parse_seller_reply("No numbers here.") is None
    assert parse_seller_reply("Price: $1200.50") == 1200.50


def test_decide_next_action_boundaries():
    rails = _simple_rails(target=450, walkaway=520)
    assert decide_next_action(450, rails) == "accept"   # exactly at target
    assert decide_next_action(380, rails) == "accept"   # below target
    assert decide_next_action(480, rails) == "counter"  # between target and walkaway
    assert decide_next_action(521, rails) == "walkaway" # above walkaway
    assert decide_next_action(520, rails) == "counter"  # exactly at walkaway -> still counter
