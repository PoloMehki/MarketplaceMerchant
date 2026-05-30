"""negotiator.py — Task 6.2: Strands agent wiring with Playwright MCP.

Builds the negotiation Agent: a Bedrock model + Playwright MCP as the managed
ToolProvider + the rails system prompt from Task 6.1. The approval_gate hook
(Task 6.3) slots into the ``hooks`` list once built.

Model-agnostic: accepts any duck-typed config and Rails objects so this lane
does not block on Dev A's models.py.

NOTE: Tasks 6.4 (reply loop) will be added to this module next.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from mcp import StdioServerParameters, stdio_client
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.tools.mcp import MCPClient


def build_mcp_client(user_data_dir: str) -> MCPClient:
    """Return a Playwright MCP client pinned to a persistent browser profile.

    The caller is responsible for opening/closing the context manager around
    the negotiation run (keep it open for the full duration -- see spec 6.2).
    """
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="npx",
                args=["@playwright/mcp@latest", "--user-data-dir", user_data_dir],
            )
        )
    )


def build_bedrock_model(config) -> BedrockModel:
    """Build a BedrockModel from the app config (region + model_id)."""
    return BedrockModel(
        region_name=config.aws_region,
        model_id=config.bedrock_model_id,
    )


def build_agent(
    bedrock_model,
    rails,
    mcp_client: MCPClient,
    *,
    hooks: Optional[list[Any]] = None,
) -> Agent:
    """Build the negotiation Agent wired to Bedrock + Playwright MCP + rails.

    The MCP context must already be open (``with mcp_client:``) before calling
    this, and must remain open for the duration of a negotiation run.

    ``hooks`` is where the HITL approval_gate (Task 6.3) is injected; pass
    ``None`` or ``[]`` for an ungated run (e.g. a deny-all test fixture).

    ``callback_handler=None`` silences the default stdout printer; the CLI
    (Task 8.1) wires its own handler.
    """
    return Agent(
        model=bedrock_model,
        system_prompt=rails.system_prompt,
        tools=[mcp_client],
        hooks=hooks or [],
        callback_handler=None,
    )


def user_data_dir_from_mcp_config(mcp_config_path: "str | Path") -> str:
    """Read the pinned --user-data-dir value out of config/mcp.json."""
    with open(mcp_config_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    args: list[str] = cfg["mcpServers"]["playwright"]["args"]
    idx = args.index("--user-data-dir")
    return args[idx + 1]
