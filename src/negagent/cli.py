"""cli.py — Task 8.1: manual-trigger end-to-end orchestrator for one listing.

Usage:
  python -m negagent.cli --spec demo.json [--location seattle]

demo.json (TargetSpec):
  {
    "query": "MacBook Pro 14 M4 32GB 1TB",
    "category": "electronics",
    "acceptable_conditions": ["good", "like new"],
    "price_mode": "below_median_pct",
    "threshold_value": 0.15,
    "time_window_minutes": 60,
    "listing_url": "https://www.facebook.com/marketplace/item/1442945257599192/"
  }
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from negagent.agent.negotiator import (
    build_accept_instruction,
    build_agent,
    build_bedrock_model,
    build_counter_instruction,
    build_instruction,
    build_mcp_client,
    build_walkaway_instruction,
    compute_counter_offer,
    decide_next_action,
    get_seller_reply,
    run_with_warmup,
    user_data_dir_from_mcp_config,
)
from negagent.agent.rails import HITLApprovalGate, build_rails
from negagent.clients.apify_client import ApifyActorClient
from negagent.clients.bedrock_client import BedrockClient
from negagent.clients.box_client import BoxArchiveClient
from negagent.config import AppConfig, load_config
from negagent.models import Comp, NegotiationState, OfferTurn, TargetSpec
from negagent.pipeline.comp_ingest import NeedsHumanReview, extract_query, score_comps
from negagent.pipeline.condition import assess_condition
from negagent.pipeline.listing_ingest import ingest_listings
from negagent.pipeline.pricing import compute_targets
from negagent.store.negotiation_repo import NegotiationRepo


def _terminal_approval(tool_name: str, tool_input: dict) -> bool:
    """HITL send-gate rendered in the terminal."""
    detail = tool_input.get("element", tool_input.get("ref", str(tool_input)))
    print(f"\n[GATE] Agent wants to call {tool_name}: {detail}", flush=True)
    try:
        return input("[GATE] Approve send? [y/N]: ").strip().lower() == "y"
    except EOFError:
        print("[GATE] Non-interactive: auto-approving send.", flush=True)
        return True


def _terminal_hitl(prompt: str) -> bool:
    """Generic yes/no HITL prompt for pipeline flags."""
    try:
        return input(f"\n[HITL] {prompt} [y/N]: ").strip().lower() == "y"
    except EOFError:
        print(f"\n[HITL] Non-interactive: auto-approving '{prompt}'", flush=True)
        return True


def run_pipeline(
    spec: TargetSpec,
    cfg: AppConfig,
    repo: NegotiationRepo,
    *,
    apify_client: Optional[Any] = None,
    bedrock_client: Optional[Any] = None,
    box_client: Optional[Any] = None,
    mcp_client: Optional[Any] = None,
    approval_fn: Optional[Callable] = None,
    hitl_fn: Optional[Callable] = None,
    location: str = "seattle",
    poll_interval_s: float = 30.0,
    max_turns: int = 8,
) -> Optional[dict]:
    """Core pipeline: listing → comps → pricing → negotiate → archive.

    All client arguments default to real implementations built from cfg.
    Pass mock objects for testing.

    Returns:
        Final negotiation state dict on success.
        ``{"status": "needs_human", "reason": "..."}`` when an HITL flag aborted.
        ``None`` when no listings matched.
    """
    if apify_client is None:
        apify_client = ApifyActorClient(
            ecommerce_actor_id=cfg.apify_ecommerce_actor_id,
            fb_actor_id=cfg.apify_fb_actor_id,
            token=cfg.apify_token,
            mock=cfg.mock_apify,
            mock_fixtures_dir=Path("tests/fixtures"),
        )
    if bedrock_client is None:
        bedrock_client = BedrockClient(
            model_id=cfg.bedrock_model_id,
            region=cfg.aws_region,
        )
    if box_client is None:
        box_client = BoxArchiveClient(
            root_folder_id=cfg.box_root_folder_id,
            client_id=cfg.box_client_id,
            client_secret=cfg.box_client_secret,
            jwt_config_path=cfg.box_jwt_config_path,
            developer_token=cfg.box_developer_token,
        )
    if approval_fn is None:
        approval_fn = _terminal_approval
    if hitl_fn is None:
        hitl_fn = _terminal_hitl

    # ── 1. Listing ingestion ────────────────────────────────────────────────
    print(f"\n[1/5] Searching FB Marketplace: {spec.query!r} in {location}...")
    listings = ingest_listings(apify_client, spec, location)
    if not listings:
        print("      No listings found.")
        return None

    if spec.listing_url:
        # Strip tracking params so URL comparison is stable
        target_url = spec.listing_url.split("?")[0].rstrip("/")
        matched = [l for l in listings if l.url.split("?")[0].rstrip("/") == target_url]
        if not matched:
            print(f"      ERROR: pinned listing URL not found in Apify results.")
            print(f"        Wanted: {spec.listing_url}")
            print(f"        Got:    {[l.url for l in listings]}")
            return None
        listing = matched[0]
    else:
        listing = listings[0]

    print(f"      → {listing.title!r}  ${listing.price:.0f}  [{listing.stated_condition}]")
    print(f"        {listing.url}")

    # ── 2. Comp ingestion + match scoring ───────────────────────────────────
    print(f"\n[2/5] Extracting search query and scoring comps...")
    structured_q = extract_query(listing, bedrock_client)
    # Use spec.query as the e-commerce search term — it's more reliable than
    # AI-extracted query when the FB listing has sparse/missing title data.
    ecomm_query = spec.query
    print(f"      Query: {ecomm_query!r}")

    raw_comps = apify_client.run_ecommerce_comps(ecomm_query)

    def _parse_price(val) -> float:
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        import re as _re
        cleaned = _re.sub(r"[^\d.]", "", str(val))
        return float(cleaned) if cleaned else 0.0

    def _extract_comp_price(c: dict) -> float:
        # real eBay actor nests price under offers.price
        offers = c.get("offers")
        if isinstance(offers, dict):
            return _parse_price(offers.get("price"))
        return _parse_price(c.get("price"))

    comps_unscored = [
        Comp(
            source=c.get("source", "ebay"),
            title=c.get("name", c.get("title", "")),
            price=_extract_comp_price(c),
            condition=c.get("condition", ""),
            url=c.get("url", ""),
        )
        for c in raw_comps
        if _extract_comp_price(c) > 0
    ]

    # Sanity filter: reject comps priced implausibly far from the listing.
    # Catches parts/accessories that share keywords but aren't the item itself.
    if listing.price > 0:
        _min_sane = listing.price * 0.50
        _max_sane = listing.price * 4.0
        comps_unscored = [c for c in comps_unscored if _min_sane <= c.price <= _max_sane]
        print(f"      {len(comps_unscored)} comps in sane price range (${_min_sane:.0f}–${_max_sane:.0f}).")
        for c in comps_unscored:
            print(f"        [comp] ${c.price:.0f}  {c.title[:60]}")

    try:
        comps = score_comps(
            listing, comps_unscored, bedrock_client,
            threshold=cfg.match_confidence_threshold,
        )
        print(f"      {len(comps)}/{len(comps_unscored)} comps passed confidence threshold.")
    except NeedsHumanReview as exc:
        print(f"\n      [FLAG] {exc}")
        if not hitl_fn("Too few confident comps — pricing baseline unreliable. Proceed anyway?"):
            return {"status": "needs_human", "reason": "match_flag"}
        comps = comps_unscored

    # ── 3. Condition assessment ─────────────────────────────────────────────
    print(f"\n[3/5] Assessing condition via vision...")
    assessment = assess_condition(listing, bedrock_client)
    print(
        f"      Stated: {listing.stated_condition!r}  →  "
        f"Assessed: {assessment.assessed_condition!r}  "
        f"(conf={assessment.confidence:.0%})"
    )
    if assessment.disagrees:
        print(f"      [FLAG] {assessment.rationale}")
        if not hitl_fn(
            f"Condition disagreement: seller says '{listing.stated_condition}', "
            f"vision says '{assessment.assessed_condition}'. Continue?"
        ):
            return {"status": "needs_human", "reason": "condition_flag"}

    # ── 4. Price targets ────────────────────────────────────────────────────
    print(f"\n[4/5] Computing price targets...")
    targets = compute_targets(comps, spec, listing_price=listing.price)
    print(f"      Good price: ${targets.good_price:.0f}")
    print(
        f"      Anchor: ${targets.anchor:.0f}  →  "
        f"Target: ${targets.target:.0f}  →  "
        f"Walk-away: ${targets.walkaway:.0f}"
    )

    listing_id = listing.fb_id or listing.url
    try:
        repo.create(listing_id, status="active", current_offer=listing.price)
    except ValueError:
        repo.reset(listing_id)
        repo.update_state(listing_id, "active", current_offer=listing.price)

    # ── 5. Negotiate ────────────────────────────────────────────────────────
    print(f"\n[5/5] Starting negotiation agent (listing_id={listing_id!r})...")
    rails = build_rails(targets, listing, comps)
    gate = HITLApprovalGate(approval_fn)

    if mcp_client is None:
        user_data_dir = user_data_dir_from_mcp_config(cfg.mcp_config_path)
        mcp_client = build_mcp_client(user_data_dir)

    bedrock_model = build_bedrock_model(cfg)
    agent = build_agent(bedrock_model, rails, mcp_client, hooks=[gate])

    # instruction = (
    #     f"Navigate to the Facebook Marketplace listing at {listing.url}. "
    #     "Click the 'Message' button to open a chat with the seller. "
    #     "A chat panel or new tab may open — follow it. "
    #     "Once the message composer is visible, type your opening offer: "
    #     "open with your anchor price and be friendly. "
    #     "Then click 'Send message' to send it. "
    #     "Follow your rails exactly — never reveal your ceiling or internal targets."
    # )
    # opening_message = (
    #     f"Hi! I'm interested in your {listing.title}. "
    #     f"Would you accept ${targets.anchor:.0f}?"
    # )
    # instruction = (
    #     f"Go to {listing.url}. "
    #     f"Wait for the page to fully load. "
    #     "Find and click the 'Message' button or 'Chat with seller' button on the listing. "
    #     "If a login modal appears, stop and report 'login_required'. "
    #     "If a chat panel opens in the same page, use it. "
    #     "If a new tab or window opens, switch to it. "
    #     "Wait until a message input field is visible and interactable. "
    #     f"Type exactly this message into the input field: '{opening_message}' "
    #     "Do not modify the message. "
    #     "Click the 'Send' or 'Send message' button to submit it. "
    #     "Confirm the message appears in the chat thread, then report 'success'. "
    #     "If any step fails, report the step name and the error."
    # )

    instruction = build_instruction(listing, targets)

    try:
        run_with_warmup(agent, listing.url, instruction)
        repo.append_turn(listing_id, "buyer", targets.anchor, f"Opening offer: ${targets.anchor:.0f}")

        # ── 5b. Reply loop ──────────────────────────────────────────────────
        print(f"\n[REPLY LOOP] Polling every {poll_interval_s:.0f}s for seller reply (max {max_turns} turns)...")
        seen_prices: set[float] = {targets.anchor}  # don't re-act on our own price
        final_action = None

        for turn_num in range(1, max_turns + 1):
            print(f"  Turn {turn_num}/{max_turns}: waiting {poll_interval_s:.0f}s...", flush=True)
            time.sleep(poll_interval_s)

            seller_offer = get_seller_reply(agent)

            if seller_offer is None or seller_offer in seen_prices:
                print("  No new seller price yet. Continuing to poll...")
                continue

            seen_prices.add(seller_offer)
            print(f"  Seller offer: ${seller_offer:.0f}", flush=True)

            repo.append_turn(listing_id, "seller", seller_offer, f"Seller: ${seller_offer:.0f}")
            repo.set_best_price(listing_id, seller_offer)

            action = decide_next_action(seller_offer, rails)
            print(f"  Decision: {action}", flush=True)

            if action == "accept":
                agent(build_accept_instruction())
                repo.update_state(listing_id, "accepted", current_offer=seller_offer)
                print("  Deal accepted!")
                final_action = "accept"
                break
            elif action == "walkaway":
                agent(build_walkaway_instruction())
                repo.update_state(listing_id, "walked")
                print("  Walked away.")
                final_action = "walkaway"
                break
            else:  # counter
                next_offer = compute_counter_offer(seller_offer, rails)
                print(f"  Countering at ${next_offer:.0f}...")
                agent(build_counter_instruction(next_offer))
                repo.append_turn(listing_id, "buyer", next_offer, f"Counter: ${next_offer:.0f}")
                repo.update_state(listing_id, "active", current_offer=next_offer)
                seen_prices.add(next_offer)

        if final_action is None:
            print(f"  Max turns reached without resolution.")

    finally:
        mcp_client.stop(None, None, None)

    # ── Archive + report ────────────────────────────────────────────────────
    state_dict = repo.get(listing_id)
    if state_dict:
        best = state_dict.get("best_price_found")
        status = state_dict.get("status", "unknown")
        print(f"\n{'='*40}")
        print(f"Negotiation complete")
        print(f"  Status:     {status}")
        print(f"  Best price: ${best:.0f}" if best else "  Best price: —")

        turns_raw = state_dict.get("turns") or []
        turns = [
            OfferTurn(
                role=t["role"],
                amount=t.get("amount"),
                message=t.get("message", ""),
                ts=t["ts"],
            )
            for t in turns_raw
        ]
        neg_state = NegotiationState(
            listing_id=listing_id,
            status=status,
            current_offer=state_dict.get("current_offer"),
            best_price_found=best,
            turns=turns,
        )
        archived = box_client.archive_negotiation(neg_state)
        print("  Box:        archived" if archived else "  Box:        skipped (see above)")

    return state_dict


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m negagent.cli",
        description="Run a negotiation for one FB Marketplace listing.",
    )
    parser.add_argument("--spec", required=True, help="Path to TargetSpec JSON file.")
    parser.add_argument("--location", default="seattle", help="FB Marketplace location.")
    parser.add_argument("--poll-interval", type=float, default=30.0,
                        help="Seconds between seller-reply polls (default 30).")
    parser.add_argument("--max-turns", type=int, default=8,
                        help="Max negotiation turns before walking away (default 8).")
    args = parser.parse_args(argv)

    try:
        spec = TargetSpec(**json.loads(Path(args.spec).read_text()))
    except Exception as exc:
        print(f"Error loading spec: {exc}", file=sys.stderr)
        return 1

    try:
        cfg = load_config()
    except Exception as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    repo = NegotiationRepo.open(cfg.sqlite_path)
    try:
        result = run_pipeline(
            spec, cfg, repo,
            location=args.location,
            poll_interval_s=args.poll_interval,
            max_turns=args.max_turns,
        )
        return 0 if result is not None else 1
    finally:
        repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
