"""Task 1.2 manual verify: create a fake negotiation, append turns, print the row.

Uses an in-memory SQLite DB, so it leaves nothing behind and needs no .env.
Run:  python scripts/verify_stage1_store.py
"""
import json

from negagent.store.negotiation_repo import NegotiationRepo

LISTING_ID = "FB-LISTING-123"


def _show(label: str, record: dict) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(record, indent=2))


def main() -> int:
    repo = NegotiationRepo.open(":memory:")

    record = repo.create(LISTING_ID)
    _show("after create", record)

    repo.append_turn(LISTING_ID, "buyer", 100.0, "Hi! Would you take $100?")
    record = repo.append_turn(
        LISTING_ID, "seller", 130.0, "Thanks for your interest - I can do $130."
    )
    _show("after two turns", record)

    # Best-price tracking: only a new minimum should stick (expect 115.0).
    repo.set_best_price(LISTING_ID, 130.0)
    repo.set_best_price(LISTING_ID, 115.0)  # lower  -> updates
    record = repo.set_best_price(LISTING_ID, 125.0)  # higher -> ignored
    _show("after best-price updates (expect best_price_found = 115.0)", record)

    record = repo.update_state(LISTING_ID, "accepted", current_offer=115.0)
    _show("after accept", record)

    repo.close()
    print("\nOK - store CRUD + best-price logic exercised on an in-memory DB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
