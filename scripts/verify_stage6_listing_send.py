"""verify_stage6_listing_send.py — test sending a message FROM a listing page.

Navigates to a real FB Marketplace listing, clicks the Message button,
waits for the chat composer to appear, and sends ONE opening offer.
Auto-approves the first send, auto-denies all subsequent ones.

Prerequisites:
  - .fb-profile/ is logged into your buyer Facebook account.
  - .env is filled in (APIFY_TOKEN, AWS credentials, etc.)

Usage:
  python scripts/verify_stage6_listing_send.py <listing_url>

Example:
  python scripts/verify_stage6_listing_send.py "https://www.facebook.com/marketplace/item/874831618260870/"
"""
import sys
from types import SimpleNamespace

from strands.hooks import BeforeToolCallEvent

from negagent.agent.negotiator import (
    build_agent,
    build_bedrock_model,
    build_instruction,
    build_mcp_client,
    run_with_warmup,
    user_data_dir_from_mcp_config,
)
from negagent.agent.rails import build_rails
from negagent.config import load_config

_SEND_TOOLS = frozenset({"browser_fill_form", "browser_press_key"})


def _make_terminal_gate():
    def gate(event: BeforeToolCallEvent) -> None:
        if event.tool_use["name"] not in _SEND_TOOLS:
            return
        tool = event.tool_use["name"]
        inp = event.tool_use.get("input", {})
        print(f"\n[GATE] Agent wants to call: {tool}")
        print(f"       Input: {inp}")
        answer = input("  Approve? [y/N]: ").strip().lower()
        if answer != "y":
            event.cancel_tool = "Human rejected. Revise and try again."

    return gate


def main(argv: list[str]) -> int:
    if len(argv) < 1:
        print(__doc__)
        print("Error: listing_url argument required.", file=sys.stderr)
        return 1

    listing_url = argv[0]
    cfg = load_config()
    user_data_dir = user_data_dir_from_mcp_config(cfg.mcp_config_path)

    print(f"Using browser profile: {user_data_dir}")
    print(f"Targeting listing:     {listing_url}")
    print("\n*** ONE real message will be sent. ***\n")

    targets = SimpleNamespace(good_price=20, anchor=15, target=25, walkaway=35)
    listing = SimpleNamespace(
        title="Cat item",
        price=40,
        stated_condition="used - good",
        url=listing_url,
    )
    comps = [
        SimpleNamespace(
            title="Similar cat item", price=25, condition="good",
            source="ebay", matched=True, match_confidence=0.9,
        ),
    ]
    rails = build_rails(targets, listing, comps)

    bedrock_model = build_bedrock_model(cfg)
    mcp_client = build_mcp_client(user_data_dir)
    gate = _make_terminal_gate()

    print("Opening Playwright MCP browser...")
    agent = build_agent(bedrock_model, rails, mcp_client, hooks=[gate])

    instruction = build_instruction(listing, targets)
    print(f"\nInstruction:\n  {instruction}\n")

    try:
        run_with_warmup(agent, listing_url, instruction)
    finally:
        mcp_client.stop(None, None, None)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
