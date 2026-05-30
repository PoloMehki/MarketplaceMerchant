"""Tasks 2.1 + 3.1: Apify client wrapper tests."""
import json
from pathlib import Path
from unittest.mock import MagicMock

from negagent.clients.apify_client import ApifyActorClient

FIXTURES = Path(__file__).parent / "fixtures"
ECOMMERCE = json.loads((FIXTURES / "ecommerce_comps.json").read_text())
FB_LISTINGS = json.loads((FIXTURES / "fb_listings.json").read_text())


def _sdk_returning(items):
    sdk = MagicMock()
    sdk.actor.return_value.call.return_value = {"defaultDatasetId": "ds1"}
    sdk.dataset.return_value.list_items.return_value.items = items
    return sdk


# --- Task 2.1: e-commerce comps ---

def test_run_ecommerce_comps_uses_keyword_input():
    """Sends keyword + marketplaces + maxProductResults to the actor."""
    sdk = _sdk_returning(ECOMMERCE)
    client = ApifyActorClient(
        ecommerce_actor_id="apify/e-commerce-scraping-tool",
        fb_actor_id="apify/facebook-marketplace-scraper",
        sdk=sdk,
    )

    items = client.run_ecommerce_comps("iphone 13")

    assert items == ECOMMERCE
    sdk.actor.assert_called_once_with("apify/e-commerce-scraping-tool")
    _, kwargs = sdk.actor.return_value.call.call_args
    run_input = kwargs["run_input"]
    assert run_input["keyword"] == "iphone 13"
    assert "marketplaces" in run_input
    assert "maxProductResults" in run_input


def test_mock_ecommerce_short_circuits_to_fixture():
    """In mock mode it loads the fixture and never touches the SDK."""
    sdk = MagicMock()
    client = ApifyActorClient(
        ecommerce_actor_id="x", fb_actor_id="y", sdk=sdk,
        mock=True, mock_fixtures_dir=FIXTURES,
    )

    items = client.run_ecommerce_comps("anything")

    assert items == ECOMMERCE
    sdk.actor.assert_not_called()


# --- Task 3.1: FB Marketplace ---

def test_run_fb_marketplace_builds_search_url():
    """Constructs the FB Marketplace search URL and passes it as startUrls."""
    sdk = _sdk_returning(FB_LISTINGS)
    client = ApifyActorClient(
        ecommerce_actor_id="x",
        fb_actor_id="apify/facebook-marketplace-scraper",
        sdk=sdk,
    )

    items = client.run_fb_marketplace("iphone 13", location="seattle")

    assert items == FB_LISTINGS
    sdk.actor.assert_called_once_with("apify/facebook-marketplace-scraper")
    _, kwargs = sdk.actor.return_value.call.call_args
    run_input = kwargs["run_input"]
    start_urls = run_input["startUrls"]
    assert len(start_urls) == 1
    assert "seattle" in start_urls[0]["url"]
    assert "iphone+13" in start_urls[0]["url"] or "iphone%2013" in start_urls[0]["url"] or "iphone 13" in start_urls[0]["url"]
    assert run_input.get("includeListingDetails") is True


def test_run_fb_marketplace_filters_by_condition():
    """Listings whose condition is not in acceptable_conditions are excluded."""
    sdk = _sdk_returning(FB_LISTINGS)
    client = ApifyActorClient(
        ecommerce_actor_id="x",
        fb_actor_id="apify/facebook-marketplace-scraper",
        sdk=sdk,
    )

    # "For parts or not working" should be excluded
    items = client.run_fb_marketplace(
        "iphone 13",
        location="seattle",
        acceptable_conditions=["good", "used - like new"],
    )

    assert len(items) == 2
    for item in items:
        assert item["condition"].lower() in ["good", "used - like new"]


def test_mock_fb_short_circuits_to_fixture():
    """In mock mode it loads the FB fixture and never touches the SDK."""
    sdk = MagicMock()
    client = ApifyActorClient(
        ecommerce_actor_id="x", fb_actor_id="y", sdk=sdk,
        mock=True, mock_fixtures_dir=FIXTURES,
    )

    items = client.run_fb_marketplace("iphone 13", location="seattle")

    assert items == FB_LISTINGS
    sdk.actor.assert_not_called()
