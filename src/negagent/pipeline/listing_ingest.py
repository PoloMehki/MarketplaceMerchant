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


def _parse_fb_price(raw: dict) -> float:
    lp = raw.get("listingPrice", {})
    if lp:
        try:
            return float(lp.get("amount", 0))
        except (TypeError, ValueError):
            pass
    try:
        return float(raw.get("price", 0))
    except (TypeError, ValueError):
        return 0.0


def _raw_to_listing(raw: dict) -> Listing:
    """Map an Apify FB Marketplace item dict to a Listing model."""
    desc = raw.get("description", raw.get("desc", ""))
    if isinstance(desc, dict):
        desc = desc.get("text", "")

    photos = raw.get("listingPhotos", [])
    image_urls = [p["image"]["uri"] for p in photos if p.get("image", {}).get("uri")]
    if not image_urls:
        image_urls = raw.get("images", raw.get("imageUrls", []))

    return Listing(
        fb_id=str(raw.get("id", raw.get("listingId", ""))),
        title=raw.get("listingTitle", raw.get("title", "")),
        desc=desc,
        price=_parse_fb_price(raw),
        stated_condition=raw.get("condition", "unknown"),
        image_urls=image_urls,
        seller=raw.get("sellerName", raw.get("seller", "")),
        url=raw.get("itemUrl", raw.get("url", raw.get("listingUrl", ""))),
    )
