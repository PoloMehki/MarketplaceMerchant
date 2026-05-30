"""verify_stage2_query.py — manual: print the structured query for a sample listing.

1 Bedrock call. Requires AWS creds + BEDROCK_MODEL_ID in .env.

Usage:
    python scripts/verify_stage2_query.py
"""
import os
import sys

from dotenv import load_dotenv

from negagent.clients.bedrock_client import BedrockClient
from negagent.models import Listing
from negagent.pipeline.comp_ingest import extract_query


def main() -> int:
    load_dotenv()
    region = os.environ.get("AWS_REGION")
    model_id = os.environ.get("BEDROCK_MODEL_ID")
    if not region or not model_id:
        print("ERROR: set AWS_REGION and BEDROCK_MODEL_ID in .env")
        return 1

    listing = Listing(
        fb_id="fb_demo",
        title="iPhone 13 128GB Midnight - Unlocked, great condition",
        desc="Selling my iPhone 13 128GB in midnight black. Unlocked, works on all carriers. "
             "Minor scratches on the back, screen is perfect. Comes with original charger.",
        price=320.0,
        stated_condition="good",
        image_urls=[],
        seller="Demo Seller",
        url="https://facebook.com/marketplace/item/demo",
    )

    bc = BedrockClient(model_id=model_id, region=region)
    result = extract_query(listing, bedrock=bc)

    print(f"brand:        {result.brand}")
    print(f"model:        {result.model}")
    print(f"condition:    {result.condition}")
    print(f"attributes:   {result.attributes}")
    print(f"search_query: {result.search_query}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
