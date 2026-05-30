"""verify_stage4_condition.py — manual: print stated vs assessed condition and flag.

1 Bedrock vision call. Uses a real public iPhone image URL (no FB auth needed).
Requires AWS creds + BEDROCK_MODEL_ID in .env.

Usage:
    python scripts/verify_stage4_condition.py
"""
import os
import sys

from dotenv import load_dotenv

from negagent.clients.bedrock_client import BedrockClient
from negagent.models import Listing
from negagent.pipeline.condition import assess_condition


def main() -> int:
    load_dotenv()
    region = os.environ.get("AWS_REGION")
    model_id = os.environ.get("BEDROCK_MODEL_ID")
    if not region or not model_id:
        print("ERROR: set AWS_REGION and BEDROCK_MODEL_ID in .env")
        return 1

    # Public product image from Amazon (no auth required)
    listing = Listing(
        fb_id="fb_demo",
        title="iPhone 13 128GB Midnight - Unlocked",
        desc="Minor scratches on the back, screen is perfect. Works great.",
        price=320.0,
        stated_condition="good",
        image_urls=[
            "https://m.media-amazon.com/images/I/61bK6PMOC3L._AC_SX679_.jpg",
        ],
        seller="Demo Seller",
        url="https://facebook.com/marketplace/item/demo",
    )

    bc = BedrockClient(model_id=model_id, region=region)
    result = assess_condition(listing, bedrock=bc)

    print(f"stated_condition:   {listing.stated_condition}")
    print(f"assessed_condition: {result.assessed_condition}")
    print(f"confidence:         {result.confidence:.2f}")
    print(f"disagrees:          {result.disagrees}")
    print(f"rationale:          {result.rationale}")
    print()
    if result.disagrees:
        print("→ Would flag for HITL review (stated_condition unchanged)")
    else:
        print("→ Agreement — pipeline continues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
