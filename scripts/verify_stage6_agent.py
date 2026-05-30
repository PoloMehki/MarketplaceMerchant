"""Task 6.2 / 6.3 manual verify: agent reads a Messenger thread and drafts an
opening offer without sending (a deny-all gate blocks every send).

Prerequisites (Task 0.3 must be done first):
  - .fb-profile/ is logged into your buyer Facebook account (cold restart stays
    logged in -- verify with the steps in config/fb-login.md).
  - You have an open Messenger thread with the test seller (teammate).
  - Your .env is filled in (python -m negagent.config --print should look good).

Usage:
  python scripts/verify_stage6_agent.py <messenger_thread_url>

Example:
  python scripts/verify_stage6_agent.py "https://www.messenger.com/t/123456789"

The agent will:
  1. Open the Playwright MCP browser (using .fb-profile -- already logged in).
  2. Navigate to the Messenger thread and read its current state.
  3. Draft an opening offer based on the sample price targets below.
  4. The deny-all gate blocks the send -- nothing is posted for real.
  5. Print the drafted message so you can inspect it.

To test approving a send (Task 6.3 live verify), answer 'y' at the prompt.
"""
import sys
from types import SimpleNamespace

from negagent.agent.negotiator import (
    build_agent,
    build_bedrock_model,
    build_mcp_client,
    user_data_dir_from_mcp_config,
)
from negagent.agent.rails import build_rails
from negagent.config import load_config

# Playwright tool names that constitute a "send" action.
# browser_type submits into the composer; browser_click may hit Send.
_SEND_TOOLS = frozenset({"browser_type", "browser_click", "browser_fill_form"})


def _make_deny_gate(*, approve_once: bool = False):
    """Return a BeforeToolCallEvent hook that denies every send tool call.

    If approve_once=True, the first send is approved and all subsequent ones
    are denied -- useful for testing that a single real message posts.
    """
    approved = {"count": 0}

    def gate(event):
        if event.tool_use["name"] not in _SEND_TOOLS:
            return  # read-only tools pass through ungated
        print(f"\n[GATE] Agent wants to call: {event.tool_use['name']}")
        print(f"       Input: {event.tool_use.get('input', {})}")
        if approve_once and approved["count"] == 0:
            print("[GATE] APPROVING (approve_once=True).")
            approved["count"] += 1
            return
        answer = input("[GATE] Approve send? [y/N]: ").strip().lower()
        if answer != "y":
            event.cancel_tool = "Human denied the send. Revise and try again."
            print("[GATE] DENIED -- nothing posted.")
        else:
            print("[GATE] APPROVED.")

    return gate


def main(argv: list[str]) -> int:
    if len(argv) < 1:
        print(__doc__)
        print("Error: messenger_thread_url argument required.", file=sys.stderr)
        return 1

    thread_url = argv[0]

    # Load real config from .env.
    cfg = load_config()
    user_data_dir = user_data_dir_from_mcp_config(cfg.mcp_config_path)

    print(f"Using browser profile: {user_data_dir}")
    print(f"Targeting thread: {thread_url}")

    # Sample targets for the verify run -- replace with real PriceTargets in production.
    targets = SimpleNamespace(good_price=420, anchor=380, target=450, walkaway=520)
    listing = SimpleNamespace(
        title="Herman Miller Aeron",
        price=600,
        stated_condition="used - good",
        url=thread_url,
    )
    comps = [
        SimpleNamespace(title="Aeron Size B", price=550, condition="good",
                        source="ebay", matched=True, match_confidence=0.9),
    ]
    rails = build_rails(targets, listing, comps)

    bedrock_model = build_bedrock_model(cfg)
    mcp_client = build_mcp_client(user_data_dir)

    gate = _make_deny_gate(approve_once=False)

    print("\nOpening Playwright MCP browser (may take a few seconds)...")
    with mcp_client:
        agent = build_agent(bedrock_model, rails, mcp_client, hooks=[gate])

        instruction = (
            f"Go to the Messenger thread at {thread_url}. "
            "Read the conversation history. "
            "Then draft an opening offer message for me to review -- do NOT send yet."
        )
        print(f"\nRunning agent with instruction:\n  {instruction}\n")
        result = agent(instruction)
        print(f"\nAgent result:\n{result}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
