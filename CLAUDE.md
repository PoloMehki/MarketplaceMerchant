# CLAUDE.md — MarketplaceMerchant

Shared playbook for **both developers** and their Claude Code sessions. Read this
first. It encodes how to build this project: the rules, the lane split, the
build/test/verify loop, which skills to reach for, and how to orchestrate
sub-agents so two people (and their agents) don't collide.

---

## 1. What this is

A buyer-focused, local Python app that finds a target second-hand item on **Facebook
Marketplace**, grounds a "fair price" in active **e-commerce comps**, and runs a
**human-in-the-loop negotiation** with the seller via a **Bedrock-reasoned Strands
agent** that actuates Messenger through **Playwright MCP**. CascadiaJS hackathon
project by Arturo (Dev A) and Mehki (Dev B).

**Source-of-truth spec** (shared out-of-band — these live outside the repo, so they
won't resolve from a fresh clone; get them from your teammate):
- `~/Downloads/negotiation-agent-spec.md` — full build spec, the authority on every task ID.
- `~/Downloads/dev-a-data-and-pricing.md` — Dev A lane.
- `~/Downloads/dev-b-agent-and-negotiation.md` — Dev B lane.

### Stack
- **Python 3.11+**, package manager `uv` (or `pip`) + `venv`.
- **Agent:** `strands-agents` + `strands-agents-tools`, model provider = **Amazon Bedrock**.
- **Browser actuation:** official **Playwright MCP** (`@playwright/mcp@latest`) over stdio, as a Strands MCP tool provider.
- **State:** local **SQLite** (`sqlite3` + thin repository). No DynamoDB.
- **Comps/listings:** **Apify** actors (e-commerce + FB Marketplace).
- **Artifacts:** **Box**, archival only — never on the live negotiation path.

### Target repo layout
```
negotiation-agent/
  pyproject.toml
  .env.example
  config/mcp.json            # Playwright MCP server config (fixed user-data-dir)
  src/negagent/
    config.py                # env + run config loading            [SHARED]
    models.py                # pydantic data models                 [SHARED]
    store/{db.py, negotiation_repo.py}
    clients/{apify_client.py, bedrock_client.py, box_client.py}
    pipeline/{comp_ingest.py, listing_ingest.py, condition.py, pricing.py}
    agent/{negotiator.py, rails.py}
    cli.py                   # manual-trigger orchestrator           [PAIR]
  tests/fixtures/            # recorded JSON for actors + bedrock responses
  scripts/                   # verify_stageN_*.py (manual, NOT in CI)
```

---

## 2. Non-negotiable ground rules

1. **External I/O always behind a thin client class** (Apify / Bedrock / Box / MCP).
   No SDK call from business logic. This wrapper discipline is what makes every unit
   mockable and lets the two lanes build in parallel.
2. **Tests are `pytest`, fully mocked with recorded JSON fixtures.** No test hits a
   live network. Bar: one happy path + the key failure/branch per unit. Smoke-level
   coverage is the target, not 100%.
3. **Manual verify scripts** live in `scripts/verify_stageN_*.py`, hit the real
   services with a known input, print results for a human to eyeball. **Never run in CI.**
4. **HITL safety is the product.** Every Messenger *send* requires explicit human
   approval; read-only tools (navigate/snapshot/read) are **ungated**. Condition
   analysis and match scoring **flag for a human — never silently overwrite/proceed**.
   Numeric guardrails (`validate_offer`) are enforced in **code**, not just the prompt.
5. **FB ToS:** automating your own Facebook account is against FB ToS regardless of
   intent. v1 keeps a human on every send and is proof-of-concept / personal use only.
6. **Shared files `config.py` and `models.py`:** **append your own fields only.**
   Expect a rebase. Freeze the shapes together before splitting (see §3).
7. **`MOCK_APIFY=true` is the default dev mode** — short-circuits Apify calls to
   fixtures so the pipeline is demoable without burning credits. Mirror this pattern
   for any new paid external call.

---

## 3. Two-developer lane split (the core orchestration)

Almost every task is **independent and mockable against fixtures** — neither dev
waits on the other's live code. Mock the other side and keep moving.

| | **Dev A — Data & Pricing** (Arturo) | **Dev B — Agent & Negotiation** (Mehki) |
|---|---|---|
| **Builds first, together** | 1.1 Pydantic models | 0.1 Config loading |
| **Then owns** | 0.2 Bedrock client · 2.1 Apify e-comm wrapper · 2.2 query extraction · 2.3 match-confidence + HITL flag · 3.1 FB Marketplace wrapper · 4.1 condition vision · 5.1 price targets · 7.1 Box archival | 1.2 SQLite store/repo · 0.3 Playwright MCP session · 6.1 rails · 6.2 agent wiring · 6.3 HITL gate · 6.4 reply loop |
| **Lane shape** | Flat — all units build in any order against fixtures | Head parallel (0.3, 6.1), then a **chain**: 6.2 → 6.3 → 6.4 |

### Dependency contract
- **A provides:** `models.py` (1.1), `bedrock_client` (0.2), and pipeline outputs
  (comps, listings, condition, price targets) that feed B's rails + agent.
- **B provides:** the SQLite store (1.2) that A's match-scoring (2.3) writes
  `needs_human` state into.
- **Agree method signatures early, then mock the other side until it lands.** Don't block.

### Hot spots
- `config.py` / `models.py` — shared; append-only; coordinate before editing.
- **8.1 CLI is the integration point — pair on it, do NOT split it.**
- 3.1 has a credit-scope landmine: **verify the FB actor is `apify/`-namespace
  (maintained) early.** Community actors bill differently — if the maintained actor
  is unavailable, flag the team immediately; it's a blocker, not a code problem.

---

## 4. Build / test / verify loop

```bash
# setup (once)
uv venv && source .venv/bin/activate
uv pip install -e .            # deps from pyproject.toml
cp .env.example .env           # fill secrets; keep MOCK_APIFY=true for dev

# inner loop
pytest -q                      # mocked, fast, offline — run constantly
pytest tests/test_<unit>.py    # the unit you're on

# wiring to real services (manual, by a human, not CI)
python scripts/verify_stage2_apify.py "<query>"
python -m negagent.cli --spec demo.json     # full end-to-end (Stage 8)
```

The rhythm for every task: **build against a fixture → mocked `pytest` green →
write/run the `verify_stageN_*.py` against the real service once before calling it
done.** "Done when" criteria live per-task in the spec — honor them literally.

---

## 5. Claude Code skills — which, when

This is a **Python / Bedrock** project. Use these:

| Skill | When |
|---|---|
| `/run` | Launch & drive the CLI or a `verify_stageN_*.py` script to see a change actually work. |
| `/verify` | Prove a change does what it should by running it end-to-end and observing behavior. |
| `/code-review` | Review the current diff before merging a stage. `/code-review ultra` = deep multi-agent cloud review of a branch/PR before integration — worth it for the Stage 6 chain and the 8.1 merge. |
| `/security-review` | Run on **Stage 6** (send gate, rails, browser actuation) and anything touching Box/Bedrock auth — the highest-risk surface in the build. |
| `/simplify` | Quality cleanup pass after a stage lands (reuse / dedupe / altitude). |
| `/loop` | Poll the seller-reply loop or re-run a verify on an interval during demo rehearsal. |
| `/init` | Already done — this file. Re-run only after a major structural change. |

**Do NOT misfire these:**
- `claude-api` is **Anthropic-SDK specific** — this project uses **Bedrock via
  `strands-agents`**, not the Anthropic SDK. Don't invoke it for our model calls.
- All `vercel:*` and Figma skills are **irrelevant** here (no Vercel/Next.js, no
  design work). Ignore them.
- `/schedule` — skip for a hackathon; only for genuine recurring obligations.

---

## 6. Multi-agent orchestration playbook

The spec is engineered for fan-out: independent, fixture-backed units. Exploit that.

**Map before you build.** Launch **Explore sub-agents (read-only, up to 3 in
parallel)** to learn existing patterns before writing code — e.g. one on the
`clients/` wrappers, one on `pipeline/` modules, one on test/fixture conventions.
Use **a Plan sub-agent** to design a stage before implementing it.

**Parallelize independent units.** Dev A's `2.1 / 4.1 / 5.1 / 7.1` share no files
and each builds against fixtures — they can be built by **`general-purpose`
sub-agents running in parallel**. Give each agent a tight task **plus the frozen
`models.py` shapes** so outputs line up.

**Serialize what must be serial.** Do **not** parallelize:
- Anything touching the **shared files** `config.py` / `models.py` — append-only,
  one writer at a time, coordinate.
- Dev B's **`6.2 → 6.3 → 6.4` chain** — each builds on the last.

**Pair, don't split, on `8.1 CLI`** — it's the integration seam.

**Isolate parallel builders.** When running multiple builder agents at once, give
each its own git worktree (`isolation: "worktree"` on the Agent tool) so they don't
step on the shared working tree; merge their branches deliberately.

> Rule of thumb: **parallelize independent fixture-backed units · serialize
> shared-file edits and dependency chains · pair on the CLI.**

---

## 7. Demo-day pre-flight (run BEFORE judging)

1. Playwright MCP profile (`.fb-profile`, pinned `--user-data-dir`) is logged into
   the **buyer** account; a cold restart lands logged-in (Task 0.3).
2. Teammate **seller** has the test listing posted, live, reachable from the buyer's Messenger.
3. Bedrock / Apify / Box smoke scripts (`verify_stage0/2/3/7`) all pass on the
   **demo laptop and network**.
4. A `demo.json` `TargetSpec` is prepared and its query is known to return the teammate's listing.
5. **Fallback ready:** if live Messenger automation misbehaves, have a recorded run
   (SQLite state + Box transcript) to show the completed negotiation.
