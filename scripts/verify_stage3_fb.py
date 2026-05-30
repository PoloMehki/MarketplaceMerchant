"""verify_stage3_fb.py — manual: run the real FB Marketplace actor, print listings.

Hits the REAL Apify service (unless MOCK_APIFY=true). Run by a human, never in CI.
Requires env vars (see .env.example):
    APIFY_TOKEN, APIFY_FB_ACTOR_ID
    MOCK_APIFY (optional; "true" short-circuits to tests/fixtures)

Usage:
    python scripts/verify_stage3_fb.py "iphone 13" --location seattle
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from negagent.clients.apify_client import ApifyActorClient

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def main(argv: list[str]) -> int:
    load_dotenv()
    if len(argv) < 2:
        print('usage: python scripts/verify_stage3_fb.py "<query>" [--location CITY]')
        return 1

    query = argv[1]
    location = "seattle"
    if "--location" in argv:
        idx = argv.index("--location")
        location = argv[idx + 1]

    mock = os.environ.get("MOCK_APIFY", "false").lower() == "true"
    client = ApifyActorClient(
        token=os.environ.get("APIFY_TOKEN"),
        ecommerce_actor_id=os.environ.get("APIFY_ECOMMERCE_ACTOR_ID", ""),
        fb_actor_id=os.environ.get("APIFY_FB_ACTOR_ID", ""),
        mock=mock,
        mock_fixtures_dir=FIXTURES if mock else None,
    )

    items = client.run_fb_marketplace(query, location=location)
    print(f"query={query!r} location={location!r} mock={mock} total={len(items)}")
    for item in items[:5]:
        print(json.dumps(item, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
