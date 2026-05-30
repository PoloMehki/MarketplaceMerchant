"""apify_client.py — Tasks 2.1 + 3.1: wraps apify-client; one method per actor.

E-commerce actor (2.1): keyword-based search via ``keyword`` + ``marketplaces``.
FB Marketplace actor (3.1): URL-based — builds the FB search URL from query +
  location, passes as ``startUrls``. Filters by ``acceptable_conditions``.

``MOCK_APIFY=true`` short-circuits both methods to committed JSON fixtures so the
pipeline runs without burning Apify credits.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus

ECOMMERCE_FIXTURE = "ecommerce_comps.json"
FB_FIXTURE = "fb_listings.json"

_DEFAULT_MARKETPLACES = ["www.amazon.com", "www.ebay.com", "www.bestbuy.com", "www.walmart.com", "www.target.com"]
_DEFAULT_MAX_PRODUCTS = 20
_DEFAULT_FB_RESULTS = 30


class ApifyActorClient:
    """Wraps the apify-client SDK; one method per actor."""

    def __init__(
        self,
        ecommerce_actor_id: str,
        fb_actor_id: str,
        token: Optional[str] = None,
        mock: bool = False,
        mock_fixtures_dir: Optional[Path] = None,
        sdk: Any = None,
    ) -> None:
        self._ecommerce_actor_id = ecommerce_actor_id
        self._fb_actor_id = fb_actor_id
        self._mock = mock
        self._mock_fixtures_dir = Path(mock_fixtures_dir) if mock_fixtures_dir else None
        if mock:
            self._sdk = sdk
        elif sdk is not None:
            self._sdk = sdk
        else:  # pragma: no cover — exercised only against real Apify
            from apify_client import ApifyClient as _SDK
            self._sdk = _SDK(token)

    def run_ecommerce_comps(
        self,
        query: str,
        marketplaces: Optional[list[str]] = None,
        max_results: int = _DEFAULT_MAX_PRODUCTS,
    ) -> list[dict]:
        """Run the e-commerce scraper; return raw dataset items.

        Actor: apify/e-commerce-scraping-tool
        Input: keyword-based search across selected marketplaces.
        """
        if self._mock:
            return self._load_fixture(ECOMMERCE_FIXTURE)
        run_input = {
            "keyword": query,
            "marketplaces": marketplaces or _DEFAULT_MARKETPLACES,
            "maxProductResults": max_results,
        }
        return self._run_actor(self._ecommerce_actor_id, run_input)

    def run_fb_marketplace(
        self,
        query: str,
        location: str,
        acceptable_conditions: Optional[list[str]] = None,
        max_results: int = _DEFAULT_FB_RESULTS,
    ) -> list[dict]:
        """Run the FB Marketplace scraper; return listings filtered by condition.

        Actor: apify/facebook-marketplace-scraper
        Input: URL-based — constructs /marketplace/{location}/search/?query=...
        """
        if self._mock:
            return self._load_fixture(FB_FIXTURE)
        url = (
            f"https://www.facebook.com/marketplace/{location}/search/"
            f"?query={quote_plus(query)}"
        )
        run_input = {
            "startUrls": [{"url": url}],
            "resultsLimit": max_results,
            "includeListingDetails": True,
        }
        items = self._run_actor(self._fb_actor_id, run_input)
        if acceptable_conditions:
            lower = {c.lower() for c in acceptable_conditions}
            items = [
                i for i in items
                if i.get("condition", "").lower() in lower
            ]
        return items

    def _run_actor(self, actor_id: str, run_input: dict) -> list[dict]:
        run = self._sdk.actor(actor_id).call(run_input=run_input)
        # call() returns a Run object; access defaultDatasetId as attribute or dict key
        dataset_id = run.default_dataset_id if hasattr(run, "default_dataset_id") else run["defaultDatasetId"]
        dataset = self._sdk.dataset(dataset_id)
        return list(dataset.list_items().items)

    def _load_fixture(self, name: str) -> list[dict]:
        if self._mock_fixtures_dir is None:
            raise ValueError("mock=True requires mock_fixtures_dir")
        return json.loads((self._mock_fixtures_dir / name).read_text())
