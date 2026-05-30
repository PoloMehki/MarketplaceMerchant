"""Task 2.2: test_extract_query_parses_json, test_extract_query_handles_garbled_json."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from negagent.models import Listing
from negagent.pipeline.comp_ingest import StructuredQuery, extract_query

FIXTURES = Path(__file__).parent / "fixtures"

SAMPLE_LISTING = Listing(
    fb_id="fb123",
    title="iPhone 13 128GB Midnight - Unlocked",
    desc="Lightly used, minor scratches on back. 128GB, unlocked, works perfectly.",
    price=350.0,
    stated_condition="good",
    image_urls=[],
    seller="Jane D.",
    url="https://facebook.com/marketplace/item/123",
)


def _bedrock_returning(fixture_name: str):
    raw = json.loads((FIXTURES / fixture_name).read_text())
    bc = MagicMock()
    bc.complete.return_value = raw["output"]["message"]["content"][0]["text"]
    return bc


def test_extract_query_parses_json():
    """Returns a StructuredQuery from a clean JSON Bedrock response."""
    bc = _bedrock_returning("bedrock_query_extraction.json")

    result = extract_query(SAMPLE_LISTING, bedrock=bc)

    assert isinstance(result, StructuredQuery)
    assert result.brand == "Apple"
    assert result.model == "iPhone 13"
    assert result.search_query == "Apple iPhone 13 128GB unlocked"
    assert result.condition == "good"
    bc.complete.assert_called_once()
    prompt_text = str(bc.complete.call_args)
    assert "iPhone 13" in prompt_text


def test_extract_query_handles_garbled_json():
    """Recovers the JSON even when Bedrock wraps it in prose."""
    bc = _bedrock_returning("bedrock_query_extraction_garbled.json")

    result = extract_query(SAMPLE_LISTING, bedrock=bc)

    assert isinstance(result, StructuredQuery)
    assert result.brand == "Apple"
    assert result.model == "iPhone 13"
    assert result.search_query == "Apple iPhone 13 128GB"


# --- Task 2.3: match-confidence scoring ---

from negagent.models import Comp
from negagent.pipeline.comp_ingest import score_comps

SAMPLE_COMPS = [
    Comp(source="amazon", title="Apple iPhone 13 128GB Unlocked", price=420.0,
         condition="renewed", url="https://amazon.com/1"),
    Comp(source="ebay", title="iPhone 13 case black", price=15.0,
         condition="new", url="https://ebay.com/2"),
]


def test_good_comps_pass_through():
    """Comps scoring above threshold are returned with match_confidence set."""
    bc = MagicMock()
    bc.complete.return_value = json.loads(
        (FIXTURES / "bedrock_match_high.json").read_text()
    )["output"]["message"]["content"][0]["text"]

    result = score_comps(SAMPLE_LISTING, SAMPLE_COMPS[:1], bedrock=bc, threshold=0.5, min_surviving=1)

    assert len(result) == 1
    assert result[0].matched is True
    assert result[0].match_confidence == 0.92


def test_low_confidence_flags_for_human():
    """When all comps score below threshold, raises NeedsHumanReview."""
    bc = MagicMock()
    bc.complete.return_value = json.loads(
        (FIXTURES / "bedrock_match_low.json").read_text()
    )["output"]["message"]["content"][0]["text"]

    from negagent.pipeline.comp_ingest import NeedsHumanReview
    with pytest.raises(NeedsHumanReview):  # 2 comps, both low — min_surviving=3 default fires
        score_comps(SAMPLE_LISTING, SAMPLE_COMPS, bedrock=bc, threshold=0.5)
