"""One-time Facebook login helper (Task 0.3).

Connects to the Playwright MCP server, opens facebook.com in the project
browser profile, and waits for you to log in by hand. When you press Enter
the browser closes and Chromium flushes the session to .fb-profile/ so every
subsequent MCP run lands pre-authenticated.

Usage:
  python scripts/fb_login.py

Do this exactly once (or again if the session expires).
"""
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters, stdio_client


async def _login(user_data_dir: str) -> None:
    server_params = StdioServerParameters(
        command="npx",
        args=["@playwright/mcp@latest", "--user-data-dir", user_data_dir],
    )
    print(f"Starting Playwright MCP with profile: {user_data_dir}")
    print("(This may take a few seconds while npx downloads/checks the package.)\n")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Connected. Opening Facebook...")
            await session.call_tool(
                "browser_navigate",
                arguments={"url": "https://www.facebook.com"},
            )
            print("\n→  A Chromium window should be open on Facebook.")
            print("→  Sign in as the BUYER account (including any 2FA).")
            print("→  Wait until you see your home feed.")
            input("\nPress Enter here once you are fully logged in: ")
            print("Closing browser (session is being saved)...")
            await session.call_tool("browser_close", arguments={})

    print(f"\nDone. Session saved to: {user_data_dir}")
    print("Verify it worked: run this script again and check you land logged-in.")
    print("Then run: python scripts/verify_stage6_agent.py <messenger_thread_url>")


def main() -> int:
    from negagent.agent.negotiator import user_data_dir_from_mcp_config
    from negagent.config import load_config, ConfigError

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    user_data_dir = user_data_dir_from_mcp_config(cfg.mcp_config_path)
    asyncio.run(_login(user_data_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
