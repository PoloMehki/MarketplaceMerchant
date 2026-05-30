"""Task 6.2: test_agent_builds_with_mocked_mcp.

(Tasks 6.4 reply-loop tests will be added with the reply loop.)
No real browser or AWS calls are made: Agent and MCPClient are patched.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from negagent.agent.negotiator import (
    build_agent,
    build_mcp_client,
    user_data_dir_from_mcp_config,
)
from negagent.agent.rails import build_rails


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
