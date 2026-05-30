"""listing_ingest.py — Stage 3 pipeline: FB Marketplace scrape → Listing records.

Calls the FB Marketplace Apify actor via ApifyActorClient and converts raw
dicts to typed Listing models. Condition filtering is applied by the Apify
client; this layer only normalises field names.
"""
from __future__ import annotations

from negagent.clients.apify_client import ApifyActorClient
from negagent.models import Listing, TargetSpec


def ingest_listings(
    client: ApifyActorClient,
    spec: TargetSpec,
    location: str = "seattle",
) -> list[Listing]:
    """Scrape FB Marketplace for spec.query; return typed Listing objects."""
    raw = client.run_fb_marketplace(
        query=spec.query,
        location=location,
        acceptable_conditions=spec.acceptable_conditions or None,
    )
    return [_raw_to_listing(item) for item in raw]


def _raw_to_listing(raw: dict) -> Listing:
    """Map an Apify FB Marketplace item dict to a Listing model."""
    return Listing(
        fb_id=str(raw.get("id", raw.get("listingId", ""))),
        title=raw.get("title", ""),
        desc=raw.get("description", raw.get("desc", "")),
        price=float(raw.get("price", 0)),
        stated_condition=raw.get("condition", "unknown"),
        image_urls=raw.get("images", raw.get("imageUrls", [])),
        seller=raw.get("sellerName", raw.get("seller", "")),
        url=raw.get("url", raw.get("listingUrl", "")),
    )
