"""negotiator.py — Tasks 6.2 + 6.4: Strands agent wiring with Playwright MCP,
and the reply read loop + turn handling.

Builds the negotiation Agent (6.2): a Bedrock model + Playwright MCP as the
managed ToolProvider + the rails system prompt from Task 6.1. The
HITLApprovalGate hook (Task 6.3, rails.py) slots into the ``hooks`` list.

Reply loop utilities (6.4): parse a Playwright thread snapshot for the seller's
latest price, decide the buyer's next action (accept / walkaway / counter), and
apply the result to NegotiationRepo state.
"""
from __future__ import annotations

import json
import re
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

    Do NOT call ``with mcp_client:`` before this. In strands v1.41, __enter__
    starts the background thread but does not set _tool_provider_started, so
    Agent.__init__ -> load_tools would try to start() again and raise. Instead,
    pass the client directly; Agent's process_tools -> load_tools -> start()
    handles startup. Call ``mcp_client.stop(None, None, None)`` in a finally
    block when the negotiation run ends.

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


# ---------------------------------------------------------------------------
# Task 6.4 — Reply read loop + turn handling
# ---------------------------------------------------------------------------

_PRICE_RE = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)")


def parse_seller_reply(snapshot: str) -> Optional[float]:
    """Return the last dollar amount in a Playwright thread snapshot, or None.

    Heuristic: the most recently visible price in a Messenger thread snapshot
    is the seller's latest counter. Returns None when the seller hasn't replied
    with a concrete number yet.
    """
    matches = _PRICE_RE.findall(snapshot)
    return float(matches[-1]) if matches else None


def decide_next_action(seller_offer: float, rails) -> str:
    """Return 'accept', 'walkaway', or 'counter' based on the seller's offer.

    Args:
        seller_offer: Price the seller just offered.
        rails: Any object with .target and .walkaway float attributes
               (the Rails dataclass from rails.py, or a duck-typed stand-in).

    Returns:
        'accept'   — seller reached or beat the target; buyer can close.
        'walkaway' — seller is above the walk-away ceiling; end negotiation.
        'counter'  — seller is between target and walkaway; keep negotiating.
    """
    if seller_offer <= float(rails.target):
        return "accept"
    if seller_offer > float(rails.walkaway):
        return "walkaway"
    return "counter"


def handle_seller_reply(
    snapshot: str,
    listing_id: str,
    repo: Any,
    rails: Any,
) -> "tuple[str, dict]":
    """Parse a thread snapshot, update repo state, and return (action, state).

    Args:
        snapshot: Raw text of a Playwright browser snapshot of the thread.
        listing_id: The negotiation to update.
        repo: NegotiationRepo (or duck-typed equivalent).
        rails: Rails object exposing .target and .walkaway.

    Returns:
        A (action, state) tuple where action is one of:
          'no_reply'  — no price found in the snapshot; state unchanged.
          'accept'    — seller at or below target; status set to 'accepted'.
          'walkaway'  — seller above walkaway; status set to 'walked'.
          'counter'   — seller between target and walkaway; status stays 'active'.
    """
    seller_offer = parse_seller_reply(snapshot)
    if seller_offer is None:
        return ("no_reply", repo.get(listing_id))

    snippet = snapshot[:300].replace("\n", " ")
    repo.append_turn(listing_id, "seller", seller_offer, snippet)
    repo.set_best_price(listing_id, seller_offer)

    action = decide_next_action(seller_offer, rails)
    if action == "accept":
        state = repo.update_state(listing_id, "accepted", current_offer=seller_offer)
    elif action == "walkaway":
        state = repo.update_state(listing_id, "walked")
    else:
        state = repo.update_state(listing_id, "active", current_offer=seller_offer)

    return (action, state)
