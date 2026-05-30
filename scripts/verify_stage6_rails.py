"""Task 6.1 manual verify: build and print the negotiation system prompt.

Uses lightweight stand-ins for PriceTargets / Listing / Comp (models.py, Task
1.1, Dev A, still pending). Run:  python scripts/verify_stage6_rails.py
"""
from types import SimpleNamespace

from negagent.agent.rails import build_rails

targets = SimpleNamespace(good_price=420, anchor=380, target=450, walkaway=520)
listing = SimpleNamespace(
    title="Herman Miller Aeron Size B",
    price=600,
    stated_condition="used - good",
    url="https://facebook.com/marketplace/item/999",
)
comps = [
    SimpleNamespace(title="Aeron Size B remastered", price=650, condition="good",
                    source="ebay", matched=True, match_confidence=0.90),
    SimpleNamespace(title="Aeron Size B classic", price=520, condition="fair",
                    source="offerup", matched=True, match_confidence=0.82),
    SimpleNamespace(title="Aeron headrest only", price=90, condition="new",
                    source="ebay", matched=False, match_confidence=0.20),
]


def main() -> int:
    rails = build_rails(targets, listing, comps)
    print(rails.system_prompt)

    print("\n" + "=" * 64)
    print("CODE-LEVEL GUARDRAILS (enforced independently of the prompt):")
    print(f"  walk-away ceiling        = ${rails.walkaway:.0f}")
    print(f"  max concession per turn  = ${rails.max_concession_per_turn:.0f}")
    for amt in (500, 520, 521, 560):
        verdict = "ALLOW" if rails.validate_offer(amt) else "REJECT"
        print(f"  validate_offer(${amt:<4}) -> {verdict}")
    print("\nExpect: offers up to $520 ALLOW, anything above $520 REJECT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
