# One-time Facebook login for the Playwright MCP profile

This is a manual, one-time step (Task 0.3). The `.fb-profile/` directory stores
the browser session so every subsequent MCP restart lands already logged in.
You do this exactly once; after that the session persists across cold restarts.

## Why the path is pinned

By default, `@playwright/mcp` keys the profile directory to a workspace hash, so
launching from a different CWD silently uses a different (logged-out) profile.
`config/mcp.json` pins `--user-data-dir` to the absolute path
`C:/Users/mehki/workplace/MarketplaceMerchant/.fb-profile` so the same
authenticated session is used regardless of where you start the process.

## One-time login steps

1. Make sure Claude Code is NOT running (or any other process using this profile).

2. Launch the Playwright MCP browser in standalone mode:

   ```
   npx @playwright/mcp@latest --user-data-dir "C:/Users/mehki/workplace/MarketplaceMerchant/.fb-profile"
   ```

   A Chromium window opens.

3. In the browser, navigate to https://www.facebook.com and sign in as the
   **buyer** account (Mehki's account), including any 2FA prompt.

4. Once you see the Facebook home feed (logged in), close the browser window.
   Chromium writes the session to `.fb-profile/` on close.

5. Verify cold-restart persistence (the "Done when" check from the spec):
   - Start the MCP browser again with the same command from step 2.
   - Navigate to https://www.facebook.com.
   - Confirm you land on the home feed WITHOUT a login prompt.
   - Close the browser.

That's it. From this point on, any process that starts Playwright MCP with
`config/mcp.json` will be logged in as the buyer account.

## Demo-day pre-flight (run this before judging)

- Run step 5 above on the demo laptop and network the morning of the demo.
- Confirm the `.fb-profile/` directory exists and is NOT gitignored-away
  (check `.gitignore` -- the directory itself is excluded from git, which is
  correct, but it must still exist on disk at the pinned path).
- If the session has expired (rare -- FB sessions are long-lived), repeat
  steps 2-4 to re-login.

## Notes

- `.fb-profile/` is in `.gitignore` (it contains your Facebook session cookie).
  Never commit it.
- Do NOT automate the login step. The persistent profile is the only supported
  mechanism for v1 (no auto-login per spec).
- If the demo is run from a different machine or path, update the
  `--user-data-dir` value in `config/mcp.json` to the correct absolute path
  on that machine, then redo the one-time login.
