# Negotiation Agent — Build Spec (v1, single-listing demo)

A buyer-focused local Python app that finds a target second-hand item on Facebook
Marketplace, grounds a "fair price" in active e-commerce comps, and runs a
human-in-the-loop negotiation with the seller via a Bedrock-reasoned agent that
actuates Messenger through Playwright MCP.

This spec is the source of truth for the coding agent. It is organized into
stages. Each stage is a vertical slice that can be built and verified on its own.
Every task lists: **Goal**, **Notes**, **Test** (mocked `pytest`), **Manual
verify** (a runnable script you operate yourself), and **Done when**.

---

## Ground rules for the implementing agent

- **Language/runtime:** Python 3.11+. Package manager: `uv` (or `pip`), `venv`.
- **Agent framework:** `strands-agents` + `strands-agents-tools`, model provider = **Amazon Bedrock**.
- **Browser actuation:** official **Playwright MCP** (`@playwright/mcp@latest`) over stdio, used as a Strands MCP tool provider.
- **External I/O is always behind an interface.** Apify, Bedrock, Box, and the MCP browser are each wrapped in a thin client class so tests can mock them. No SDK call is made directly from business logic.
- **Tests:** `pytest`. Every external call is mocked with recorded JSON fixtures. No test hits a live network. Smoke-level coverage is the bar — one happy path + the key failure/branch per unit.
- **Manual verify scripts** live in `scripts/verify_stageN_*.py`, hit the real services with a known input, and print results for a human to eyeball. These are NOT run in CI.
- **State store:** local SQLite (`sqlite3` + thin repository). No DynamoDB.
- **Artifact store:** Box, used **only** for archival (snapshots, transcripts, photos, comp dumps). Box is never on the live negotiation path.
- **Comps:** **active listings only** for v1 (asking prices skew high — see Stage 5 margin rule). Sold-comp data is a documented TODO.
- **Out of scope for v1 (documented TODOs, do not build):** parallel negotiations, Chrome extension UI, EventBridge scheduling, approved-match memory cache, sold-price comps, auto-login.

### Target repo layout

```
negotiation-agent/
  pyproject.toml
  .env.example
  config/
    mcp.json                # Playwright MCP server config (fixed user-data-dir)
  src/negagent/
    config.py               # env + run config loading
    models.py               # pydantic data models
    store/
      db.py                 # sqlite connection + schema
      negotiation_repo.py   # CRUD for negotiation state
    clients/
      apify_client.py       # wraps apify-client; one method per actor
      bedrock_client.py     # wraps Bedrock messages calls (text + vision)
      box_client.py         # wraps Box uploads
    pipeline/
      comp_ingest.py        # query extraction + comp scrape + match scoring
      listing_ingest.py     # FB Marketplace scrape -> Listing records
      condition.py          # multimodal condition check (flag, no overwrite)
      pricing.py            # "good price" / anchor / target / walkaway
    agent/
      negotiator.py         # Strands agent wiring + rails + HITL hook
      rails.py              # system prompt + numeric guardrails
    cli.py                  # manual-trigger orchestrator
  tests/
    fixtures/               # recorded JSON for actors + bedrock responses
    ...
  scripts/
    verify_stage0_*.py ...
```

---

## Stage 0 — Skeleton, secrets, and the browser session

**Outcome:** the project runs, talks to Bedrock, and has a Playwright MCP browser
that is already logged into Facebook and stays logged in across restarts.

### Task 0.1 — Project skeleton + config loading
- **Goal:** `pyproject.toml` with deps, `.env.example`, `config.py` that loads
  env vars into a typed config object (Bedrock region/model id, Apify token,
  Apify actor ids for the e-commerce + FB actors, Box auth, MCP config path,
  SQLite path, HITL on/off, match-confidence threshold, condition-tolerance).
- **Notes:** deps include `strands-agents`, `strands-agents-tools`, `mcp`,
  `apify-client`, `boxsdk` (or Box official SDK), `pydantic`, `pytest`,
  `python-dotenv`. Fail fast with a clear error if a required env var is missing.
- **Test:** `test_config_loads_from_env` (monkeypatched env) and
  `test_config_missing_required_raises`.
- **Manual verify:** `python -m negagent.config --print` prints the resolved
  config with secrets masked.
- **Done when:** config loads from `.env`; missing vars raise a named error.

### Task 0.2 — Bedrock connectivity smoke test
- **Goal:** `clients/bedrock_client.py` with `complete(messages, system=None)` and
  `complete_vision(messages_with_images)`; verify a real round-trip.
- **Notes:** use the Bedrock model id from config. Keep the wrapper dumb — it
  takes message dicts and returns text; no business logic.
- **Test:** `test_bedrock_client_parses_response` against a recorded Bedrock
  response fixture (mock the boto/SDK call).
- **Manual verify:** `scripts/verify_stage0_bedrock.py` sends "reply with OK" and
  prints the response.
- **Done when:** mocked test passes and the manual script prints a real reply.

### Task 0.3 — Playwright MCP persistent session
- **Goal:** `config/mcp.json` configures Playwright MCP with a **fixed absolute**
  `--user-data-dir` (e.g. `./.fb-profile`). Document the one-time login flow.
- **Notes / critical:** the profile location MUST be pinned with `--user-data-dir`.
  The default profile path is keyed to a workspace hash, so launching from a
  different directory silently uses a different (logged-out) profile. Pin it so
  the authenticated session is deterministic regardless of CWD. Do **not**
  automate login. The persistent profile preserves the Facebook session across
  MCP restarts; you log in by hand exactly once into that profile dir.
  Example `mcp.json`:
  ```json
  {
    "mcpServers": {
      "playwright": {
        "command": "npx",
        "args": ["@playwright/mcp@latest", "--user-data-dir", "/ABS/PATH/.fb-profile"]
      }
    }
  }
  ```
- **Test:** none (manual by nature).
- **Manual verify:** (1) start the MCP browser, navigate to facebook.com, log in
  by hand incl. 2FA; (2) stop everything; (3) restart and navigate to facebook.com
  again — confirm you are still logged in. Document this as the demo-day pre-flight.
- **Done when:** a second cold start lands on a logged-in Facebook without a login prompt.

---

## Stage 1 — Data models + SQLite state

### Task 1.1 — Pydantic models
- **Goal:** `models.py` with: `TargetSpec` (query, category, acceptable
  conditions[], price_mode [`budget` | `below_median_pct` | `below_avg_pct`],
  threshold_value, time_window_minutes), `Comp` (source, title, price, condition,
  url, matched: bool, match_confidence), `Listing` (fb_id, title, desc, price,
  stated_condition, image_urls[], seller, url), `ConditionAssessment`
  (assessed_condition, confidence, disagrees: bool, rationale),
  `PriceTargets` (good_price, anchor, target, walkaway), `OfferTurn`
  (role, amount, message, ts), `NegotiationState` (listing_id, status
  [`active`|`accepted`|`walked`|`sold`|`needs_human`], current_offer,
  best_price_found, turns: list[OfferTurn]).
- **Test:** `test_models_roundtrip` (construct, serialize, deserialize) and
  `test_price_mode_validation` (reject unknown modes).
- **Manual verify:** none needed.
- **Done when:** models serialize/deserialize and reject invalid enums.

### Task 1.2 — SQLite store + repository
- **Goal:** `store/db.py` creates schema; `store/negotiation_repo.py` provides
  `create`, `get`, `update_state`, `append_turn`, `set_best_price`.
- **Notes:** single-writer, local file. Store `turns` as a JSON column for v1.
- **Test:** `test_repo_crud` against an in-memory/tempfile SQLite — create, append
  two turns, update status, read back; assert `best_price_found` updates only when
  a lower acceptable price is seen.
- **Manual verify:** `scripts/verify_stage1_store.py` creates a fake negotiation,
  appends turns, prints the row.
- **Done when:** CRUD + best-price logic pass on a temp DB.

---

## Stage 2 — Comp ingestion (Apify e-commerce, read-only) + auto-matching

### Task 2.1 — Apify e-commerce client wrapper
- **Goal:** `clients/apify_client.py :: run_ecommerce_comps(query) -> list[raw]`.
  Calls the Apify e-commerce scraper actor synchronously, returns dataset items.
- **Notes:** actor id from config. Add a `MOCK_APIFY=true` short-circuit that
  returns a fixture, mirroring your TapFinder `MOCK_CALLS` pattern, so the rest of
  the pipeline is demoable without burning Apify credits.
- **Test:** `test_run_ecommerce_comps_parses_dataset` against a recorded actor
  output fixture (mock the apify-client run call).
- **Manual verify:** `scripts/verify_stage2_apify.py "<query>"` runs the real
  actor and prints the first 5 normalized items.
- **Done when:** mocked test passes; manual run returns real comps.

### Task 2.2 — Structured query extraction (Bedrock)
- **Goal:** `pipeline/comp_ingest.py :: extract_query(listing) -> StructuredQuery`
  (brand, model, variant attributes, condition). Bedrock turns a free-text FB
  title/description into a structured search query that drives 2.1.
- **Notes:** prompt Bedrock to return strict JSON; parse defensively (strip
  fences). Variant fields matter — they drive price (e.g. capacity, lock status).
- **Test:** `test_extract_query_parses_json` against a recorded Bedrock fixture for
  a known listing; `test_extract_query_handles_garbled_json` (Bedrock returns
  prose around JSON — parser still recovers).
- **Manual verify:** `scripts/verify_stage2_query.py` prints the structured query
  for a sample listing.
- **Done when:** structured query extracted and robust to messy model output.

### Task 2.3 — Match-confidence scoring + HITL flag
- **Goal:** `score_comps(listing, comps) -> list[Comp]` where Bedrock scores each
  comp's relevance to the target; comps below `match_confidence_threshold` are
  dropped, and if too few survive (configurable, e.g. < 3) the listing's state is
  set to `needs_human` instead of proceeding on a bad baseline.
- **Notes:** this is the correctness guard for auto-matching — wrong comps poison
  every downstream price. Mirror the condition-flag pattern: flag for a human,
  don't silently proceed.
- **Test:** `test_low_confidence_flags_for_human` (all comps score low ->
  state `needs_human`); `test_good_comps_pass_through`.
- **Manual verify:** `scripts/verify_stage2_match.py` prints kept vs dropped comps
  with scores for a sample listing + comp set.
- **Done when:** good comps pass; weak matches trigger the human flag.

---

## Stage 3 — FB listing ingestion (Apify FB Marketplace)

### Task 3.1 — FB Marketplace client wrapper
- **Goal:** `clients/apify_client.py :: run_fb_marketplace(query, location) ->
  list[Listing]`. Read-only. Returns listings matching the target query, filtered
  to the `acceptable_conditions` in `TargetSpec`.
- **Notes:** **Verify the actor is Apify-maintained (`apify/` namespace) before
  building on it** — most FB Marketplace actors are community-built and bill
  differently than your maintained-actor credits. If the maintained actor is
  unavailable, surface that to the team immediately; it's a credit-scope blocker,
  not a code problem. Same `MOCK_APIFY` short-circuit as 2.1.
- **Test:** `test_run_fb_marketplace_parses_and_filters` against a recorded
  fixture; assert listings outside the condition filter are excluded.
- **Manual verify:** `scripts/verify_stage3_fb.py "<query>"` returns real listings.
- **Done when:** mocked test passes; manual run returns real listings filtered by condition.

---

## Stage 4 — Condition analysis (Bedrock multimodal) — flag, never overwrite

### Task 4.1 — Image fetch + vision condition assessment
- **Goal:** `pipeline/condition.py :: assess_condition(listing) ->
  ConditionAssessment`. Downloads listing images, sends them + the description to
  Bedrock vision, returns an assessed condition with confidence and rationale.
- **Notes:** if the assessed condition disagrees with the seller's stated
  condition beyond `condition_tolerance`, set `disagrees=True` and route to HITL
  review. **Do not overwrite** the stored condition field automatically — the
  human decides. Used-item photos are noisy; an overconfident auto-correction
  silently poisons the target price.
- **Test:** `test_condition_agreement_no_flag` and
  `test_condition_disagreement_flags_human` against recorded vision fixtures.
- **Manual verify:** `scripts/verify_stage4_condition.py <listing_url>` prints
  stated vs assessed condition and whether it flagged.
- **Done when:** agreement passes through; disagreement flags for human review without overwriting.

---

## Stage 5 — Price intelligence

### Task 5.1 — Compute price targets from active comps
- **Goal:** `pipeline/pricing.py :: compute_targets(comps, target_spec) ->
  PriceTargets` producing `good_price`, `anchor` (opening offer), `target`
  (acceptable settle), and `walkaway` (hard ceiling).
- **Notes / active-listing skew rule:** comps are **asking** prices and skew high.
  The baseline "good price" MUST sit a configured margin **below** the active
  median/average — not at it — across **all** modes, not only the user's chosen
  `below_*_pct` mode. Map `TargetSpec.price_mode`:
  - `budget` -> `target = min(threshold_value, good_price)`, `walkaway = threshold_value`.
  - `below_median_pct` -> `target = median(comps) * (1 - pct)`.
  - `below_avg_pct` -> `target = mean(comps) * (1 - pct)`.
  `anchor` opens below `target` to leave negotiating room; `walkaway` is the
  number the agent may never cross.
- **Test:** `test_targets_below_active_median` (good_price strictly below median);
  `test_budget_mode_caps_at_threshold`; `test_walkaway_never_below_anchor` ordering
  invariants (`anchor <= target <= walkaway`).
- **Manual verify:** `scripts/verify_stage5_pricing.py` prints the four numbers for
  a sample comp set under each mode.
- **Done when:** targets computed per mode with the below-median skew enforced and ordering invariants hold.

---

## Stage 6 — Negotiation agent (Strands + Bedrock + Playwright MCP) with HITL gate

**This is the core. Build it last among the functional stages and budget the most time.**

### Task 6.1 — Rails (system prompt + numeric guardrails)
- **Goal:** `agent/rails.py` builds the negotiation system prompt from
  `PriceTargets` + listing + comps. Hard rails, stated explicitly:
  1. Never offer above `walkaway`. 2. Never disclose the maximum / budget /
  walkaway to the seller. 3. Concede no more than `max_concession_per_turn`
  between offers. 4. If the seller won't reach `target` within the rails, present
  the best achieved price to the user — do not auto-accept above `target` without
  human approval. 5. Be courteous; justify offers with the comp evidence.
  Bedrock owns tone and tactics **inside** these rails.
- **Notes:** keep numeric guardrails enforced in code too (don't trust the prompt
  alone): a `validate_offer(amount)` function rejects any drafted offer above
  `walkaway` before it can reach the send gate.
- **Test:** `test_prompt_contains_rails`; `test_validate_offer_rejects_above_walkaway`.
- **Manual verify:** print a built prompt for a sample setup and read it.
- **Done when:** prompt encodes all five rails and the code-level offer validator rejects over-ceiling offers.

### Task 6.2 — Strands agent wiring with Playwright MCP
- **Goal:** `agent/negotiator.py` builds a Strands `Agent` with the Bedrock model
  and the Playwright MCP client as a managed tool provider. Verified pattern:
  ```python
  from strands import Agent
  from strands.tools.mcp import MCPClient
  from mcp import stdio_client, StdioServerParameters

  playwright_mcp = MCPClient(lambda: stdio_client(
      StdioServerParameters(
          command="npx",
          args=["@playwright/mcp@latest", "--user-data-dir", USER_DATA_DIR],
      )
  ))

  with playwright_mcp:
      agent = Agent(
          model=bedrock_model,
          system_prompt=rails_prompt,
          tools=[playwright_mcp],          # MCPClient is a ToolProvider
          hooks=[approval_gate],           # see 6.3
      )
      result = agent(turn_instruction)
  ```
  The agent drives Messenger using the Playwright MCP browser tools
  (navigate / snapshot / type / click). Optionally add one thin custom `@tool`
  (`send_thread_message(thread_url, text)`) that wraps the browser steps for
  reliability, but the generic tools are sufficient for v1.
- **Notes:** the persistent FB profile from Task 0.3 means no login step. Keep the
  MCP context open for the duration of a negotiation.
- **Test:** `test_agent_builds_with_mocked_mcp` — mock `MCPClient`/`list_tools_sync`
  and assert the agent is constructed with the tool provider and rails prompt. Do
  not launch a real browser in tests.
- **Manual verify:** `scripts/verify_stage6_agent.py` opens the MCP browser, has
  the agent read the open Messenger thread and print a *drafted* opening offer
  **without sending** (gate denies in this script).
- **Done when:** agent constructs with Bedrock + Playwright MCP; drafts an offer from a real thread without sending.

### Task 6.3 — Human-in-the-loop approval gate (send only after approval)
- **Goal:** `approval_gate` using Strands' `BeforeToolCallEvent` hook: before any
  tool call that *sends* a message (the custom `send_thread_message` tool, or a
  `browser_type`/submit into the composer), interrupt and require explicit human
  approval; on anything other than approve, cancel the tool and feed the agent the
  rejection so it can revise.
  ```python
  from strands.hooks import BeforeToolCallEvent

  def approval_gate(event: BeforeToolCallEvent):
      if event.tool_use["name"] in SEND_TOOLS:
          decision = event.interrupt("send_approval", reason=event.tool_use["input"])
          if decision != "APPROVE":
              event.cancel_tool = "Human rejected the draft."
  ```
- **Notes:** read-only tools (navigate, snapshot, read) are NOT gated — only sends.
  The approval surfaces in the CLI (Stage 8). This is the single most important
  safety/ToS control in the build: the agent drafts, a human authorizes every send.
- **Test:** `test_gate_blocks_send_without_approval` (decision != APPROVE -> tool
  cancelled); `test_gate_allows_read_tools` (navigate/snapshot not intercepted);
  `test_gate_allows_send_on_approve`.
- **Manual verify:** in `verify_stage6_agent.py`, approve once and confirm a real
  message posts to the test thread; deny and confirm nothing posts.
- **Done when:** sends require approval; reads don't; approve posts, deny doesn't.

### Task 6.4 — Reply read loop + turn handling
- **Goal:** after a send, the agent polls the thread (via Playwright snapshot) for
  the seller's reply, parses it into an `OfferTurn`, updates `NegotiationState`
  (turn count, current offer, best_price_found), and decides next action: counter
  (within rails), accept (<= target, or human-approved), or walk away.
- **Notes:** the seller is a human responding manually on their own account/phone;
  replies are not instant. Poll with backoff and a max wait; the read half of
  Messenger automation is the fiddly part — give it explicit retry/timeout and a
  "no reply yet" state rather than hanging.
- **Test:** `test_reply_parsed_and_state_updated` (feed a recorded thread snapshot
  -> state advances); `test_walkaway_triggers_when_seller_above_ceiling`;
  `test_accept_when_at_or_below_target`.
- **Manual verify:** `scripts/verify_stage6_loop.py` runs one full send→reply→
  counter cycle against the teammate seller, printing state after each turn.
- **Done when:** a full multi-turn cycle updates state and respects accept/walkaway rules.

---

## Stage 7 — Box artifact archival (offline, never in the hot loop)

### Task 7.1 — Box client + archival writes
- **Goal:** `clients/box_client.py` uploads artifacts to a per-negotiation folder:
  listing snapshot JSON, comp dump JSON, listing photos, and the final negotiation
  transcript. Called **after** a run or turn completes — never blocking a send.
- **Notes:** keep it fire-and-forget with try/except; a Box failure must not break
  or delay a negotiation. This is archival, not state.
- **Test:** `test_box_upload_called_with_expected_payload` (mock Box SDK);
  `test_box_failure_does_not_raise_into_pipeline`.
- **Manual verify:** `scripts/verify_stage7_box.py` archives a sample negotiation
  and you confirm the files appear in Box.
- **Done when:** artifacts land in Box; a Box error is swallowed without affecting the negotiation.

---

## Stage 8 — CLI orchestrator (end-to-end, single listing)

### Task 8.1 — Manual-trigger end-to-end CLI
- **Goal:** `cli.py` runs the whole slice for ONE listing on manual trigger:
  1. Load `TargetSpec` (from flags or a small JSON). 2. `listing_ingest` -> pick
  the target listing. 3. `comp_ingest` (extract query -> scrape -> match-score;
  stop for human if flagged). 4. `condition.assess` (stop for human if flagged).
  5. `pricing.compute_targets`. 6. Run the negotiation agent loop with the HITL
  approval gate rendered in the terminal. 7. On finish, archive to Box and print
  the outcome + best price found. SQLite persists state throughout.
- **Notes:** the time window from `TargetSpec` bounds the negotiation loop; when it
  expires, present the best achieved price. HITL prompts (match flag, condition
  flag, every send approval) are simple terminal y/n/edit prompts.
- **Test:** `test_cli_happy_path_end_to_end` with ALL externals mocked
  (Apify/Bedrock/Box/MCP fixtures, auto-approve gate) — asserts the pipeline runs
  start to finish and writes a final state; `test_cli_stops_on_match_flag`;
  `test_cli_stops_on_condition_flag`.
- **Manual verify:** full live demo rehearsal — teammate posts the listing,
  operator runs `python -m negagent.cli --spec demo.json`, walks the approvals,
  seller replies manually, negotiation completes, Box shows the transcript.
- **Done when:** one command drives the full flow live with human approvals, and the mocked end-to-end test passes in CI.

---

## Demo-day pre-flight checklist (run this BEFORE judging)

1. Playwright MCP profile (`.fb-profile`) is logged into the **buyer** account; a
   cold restart lands logged-in (Task 0.3).
2. Teammate **seller** has the test listing posted and live, reachable from the
   buyer account's Messenger.
3. Bedrock, Apify, and Box smoke scripts (`verify_stage0/2/3/7`) all pass on the
   **demo laptop and network**.
4. A `demo.json` `TargetSpec` is prepared and its query is known to return the
   teammate's listing.
5. Fallback ready: if live Messenger automation misbehaves, have a recorded run
   (SQLite state + Box transcript) to show the completed negotiation.

## TODO / stretch (explicitly NOT in v1)

- Parallel negotiations across multiple listings (note: a persistent browser
  profile is single-instance — parallel needs separate profiles/sessions).
- Chrome extension UI replacing the CLI.
- Approved-match memory (write to Box, load into local cache on startup; exact-key
  match on normalized query — not Box-in-the-hot-path).
- Sold-price comps (gated eBay Marketplace Insights or a sold-filter scrape) to
  replace the active-listing skew heuristic.
- EventBridge / scheduled re-scrape instead of manual trigger.
- Honest framing for judges: automating your own Facebook account via Playwright
  is against Facebook's ToS regardless of intent or volume; v1 keeps a human in
  the loop on every send and is built for personal/proof-of-concept use. A
  production version would require a sanctioned channel.
