"""verify_stage2_match.py — manual: print kept vs dropped comps with scores.

3 Bedrock calls (one per comp). Requires AWS creds + BEDROCK_MODEL_ID in .env.

Usage:
    python scripts/verify_stage2_match.py
"""
import os
import sys

from dotenv import load_dotenv

from negagent.clients.bedrock_client import BedrockClient
from negagent.models import Comp, Listing
from negagent.pipeline.comp_ingest import NeedsHumanReview, score_comps

LISTING = Listing(
    fb_id="fb_demo",
    title="iPhone 13 128GB Midnight - Unlocked, great condition",
    desc="Selling my iPhone 13 128GB in midnight black. Unlocked, works on all carriers. "
         "Minor scratches on the back, screen is perfect.",
    price=320.0,
    stated_condition="good",
    image_urls=[],
    seller="Demo Seller",
    url="https://facebook.com/marketplace/item/demo",
)

# Mix of good comps and a bad one (case, not the phone) to test filtering
COMPS = [
    Comp(source="amazon", title="Apple iPhone 13 128GB (Renewed) Unlocked",
         price=429.99, condition="renewed", url="https://amazon.com/1"),
    Comp(source="ebay",   title="Apple iPhone 13 128GB Unlocked Midnight",
         price=389.00, condition="used",    url="https://ebay.com/2"),
    Comp(source="target", title="OtterBox iPhone 13 Case Black",
         price=24.95,  condition="new",     url="https://target.com/3"),
]

THRESHOLD = 0.5


def main() -> int:
    load_dotenv()
    region = os.environ.get("AWS_REGION")
    model_id = os.environ.get("BEDROCK_MODEL_ID")
    if not region or not model_id:
        print("ERROR: set AWS_REGION and BEDROCK_MODEL_ID in .env")
        return 1

    bc = BedrockClient(model_id=model_id, region=region)

    print(f"Listing: {LISTING.title}")
    print(f"Threshold: {THRESHOLD}  (need ≥3 to pass without human flag)\n")

    try:
        passed = score_comps(LISTING, COMPS, bedrock=bc, threshold=THRESHOLD)
        print(f"PASSED ({len(passed)}):")
        for c in passed:
            print(f"  [{c.match_confidence:.2f}] {c.title} — ${c.price}")
    except NeedsHumanReview as e:
        print(f"NEEDS HUMAN REVIEW: {e}")
        print("\nAll scored comps:")

    # also show any that were dropped (not in passed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
