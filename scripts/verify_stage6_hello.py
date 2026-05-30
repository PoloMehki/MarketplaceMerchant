"""Minimal Playwright MCP smoke test: sends 'hello' to a Messenger thread.

No agent, no Bedrock — raw MCP tool calls only. Navigates to the thread,
waits for the composer to load, extracts its ref from the accessibility
snapshot, types 'hello', and presses Enter.

Usage:
  python scripts/verify_stage6_hello.py <messenger_thread_url>
"""
import asyncio
import re
import sys

from mcp import ClientSession, StdioServerParameters, stdio_client

from negagent.agent.negotiator import user_data_dir_from_mcp_config
from negagent.config import load_config


def _extract_ref(snapshot_text: str, label: str) -> str | None:
    """Return the ref= value for an element matching label in a snapshot."""
    pattern = rf'textbox "{re.escape(label)}" \[ref=(e\d+)\]'
    m = re.search(pattern, snapshot_text)
    return m.group(1) if m else None


async def _send_hello(user_data_dir: str, thread_url: str) -> None:
    server_params = StdioServerParameters(
        command="npx",
        args=["@playwright/mcp@latest", "--user-data-dir", user_data_dir],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print(f"Navigating to {thread_url} ...")
            await session.call_tool("browser_navigate", arguments={"url": thread_url})

            # Poll until the composer appears (up to 15 s).
            composer_ref = None
            for attempt in range(5):
                print(f"Waiting for composer (attempt {attempt + 1}/5)...")
                await session.call_tool("browser_wait_for", arguments={"time": 3000})
                snap = await session.call_tool("browser_snapshot", arguments={})
                snapshot_text = str(snap)
                composer_ref = _extract_ref(snapshot_text, "Write to Mehki Polo")
                if composer_ref:
                    print(f"  Composer found: ref={composer_ref}")
                    break
            else:
                print("ERROR: composer textbox not found after 15 s. Is the profile logged in?")
                print("Snapshot tail:", snapshot_text[-600:])
                return

            print("Typing 'hello' and submitting ...")
            typ = await session.call_tool(
                "browser_type",
                arguments={
                    "target": composer_ref,
                    "text": "hello",
                    "submit": True,
                },
            )
            print(f"  type result: {typ.content[0].text[:200] if typ.content else typ}")

            print("Holding 2 s so you can see it sent...")
            await session.call_tool("browser_wait_for", arguments={"time": 2000})
            print("Done.")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        print("Error: messenger_thread_url required.", file=sys.stderr)
        return 1

    thread_url = sys.argv[1]
    cfg = load_config()
    user_data_dir = user_data_dir_from_mcp_config(cfg.mcp_config_path)
    print(f"Profile: {user_data_dir}")
    asyncio.run(_send_hello(user_data_dir, thread_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
