"""Task 6.3 live send verify: agent sends ONE real opening offer to Mehki.

Auto-approves the FIRST send tool call, auto-denies all subsequent ones so
exactly one message is posted and nothing runs away. Prints the gate decision
for every intercepted call so you can see what the agent tried to do.

Prerequisites (same as verify_stage6_agent.py):
  - .fb-profile/ is logged into your buyer Facebook account.
  - You have an open Messenger thread with the test seller (Mehki).
  - .env is filled in (python -m negagent.config --print should look good).

Usage:
  python scripts/verify_stage6_send.py <messenger_thread_url>

Example:
  python scripts/verify_stage6_send.py "https://www.facebook.com/messages/e2ee/t/1009478712029946"
"""
import sys
from types import SimpleNamespace

from strands.hooks import BeforeToolCallEvent

from negagent.agent.negotiator import (
    build_agent,
    build_bedrock_model,
    build_mcp_client,
    user_data_dir_from_mcp_config,
)
from negagent.agent.rails import build_rails
from negagent.config import load_config

_SEND_TOOLS = frozenset({"browser_type", "browser_fill_form"})


def _make_approve_once_gate():
    """Approve the first send, auto-deny all subsequent ones (no input() calls)."""
    sends_seen = {"count": 0}

    def gate(event: BeforeToolCallEvent) -> None:
        if event.tool_use["name"] not in _SEND_TOOLS:
            return
        sends_seen["count"] += 1
        n = sends_seen["count"]
        tool = event.tool_use["name"]
        inp = event.tool_use.get("input", {})
        if n == 1:
            print(f"\n[GATE] Send #{n} — AUTO-APPROVING: {tool}")
            print(f"       Input: {inp}")
        else:
            print(f"\n[GATE] Send #{n} — AUTO-DENYING: {tool}")
            print(f"       Input: {inp}")
            event.cancel_tool = "Only one send approved for this verify run."

    return gate


def main(argv: list[str]) -> int:
    if len(argv) < 1:
        print(__doc__)
        print("Error: messenger_thread_url argument required.", file=sys.stderr)
        return 1

    thread_url = argv[0]
    cfg = load_config()
    user_data_dir = user_data_dir_from_mcp_config(cfg.mcp_config_path)

    print(f"Using browser profile: {user_data_dir}")
    print(f"Targeting thread:      {thread_url}")
    print("\n*** ONE real message will be sent to Mehki. ***\n")

    targets = SimpleNamespace(good_price=420, anchor=380, target=450, walkaway=520)
    listing = SimpleNamespace(
        title="Herman Miller Aeron",
        price=600,
        stated_condition="used - good",
        url=thread_url,
    )
    comps = [
        SimpleNamespace(
            title="Aeron Size B", price=550, condition="good",
            source="ebay", matched=True, match_confidence=0.9,
        ),
    ]
    rails = build_rails(targets, listing, comps)

    bedrock_model = build_bedrock_model(cfg)
    mcp_client = build_mcp_client(user_data_dir)
    gate = _make_approve_once_gate()

    print("Opening Playwright MCP browser...")
    agent = build_agent(bedrock_model, rails, mcp_client, hooks=[gate])

    instruction = (
        f"Go to the Messenger thread at {thread_url}. "
        "Type the following message into the Messenger text box and press send: "
        "'Hi Mehki! I'm very interested in the Aeron chair. "
        "I found a comparable Aeron Size B in good condition on eBay for $550. "
        "Based on that, I'd like to offer $380 — would you consider it?' "
        "Type that exact text into the composer and send it now."
    )
    print(f"\nInstruction:\n  {instruction}\n")

    try:
        result = agent(instruction)
        print(f"\nAgent result:\n{result}")
    finally:
        mcp_client.stop(None, None, None)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
