"""Task 4.1: test_condition_agreement_no_flag, test_condition_disagreement_flags_human."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from negagent.models import ConditionAssessment, Listing
from negagent.pipeline.condition import assess_condition

FIXTURES = Path(__file__).parent / "fixtures"

SAMPLE_LISTING = Listing(
    fb_id="fb123",
    title="iPhone 13 128GB",
    desc="Good condition, minor scratches.",
    price=350.0,
    stated_condition="good",
    image_urls=["https://img.facebook.com/1.jpg", "https://img.facebook.com/2.jpg"],
    seller="Jane D.",
    url="https://facebook.com/marketplace/item/123",
)

FAKE_IMAGE_BYTES = b"\xff\xd8\xff"  # minimal JPEG header


def _bedrock_returning(fixture_name: str):
    raw = json.loads((FIXTURES / fixture_name).read_text())
    bc = MagicMock()
    bc.complete_vision.return_value = raw["output"]["message"]["content"][0]["text"]
    return bc


def test_condition_agreement_no_flag():
    """When assessed condition matches stated, disagrees=False and no flag raised."""
    bc = _bedrock_returning("bedrock_condition_agree.json")

    with patch("negagent.pipeline.condition._fetch_image", return_value=FAKE_IMAGE_BYTES):
        result = assess_condition(SAMPLE_LISTING, bedrock=bc)

    assert isinstance(result, ConditionAssessment)
    assert result.assessed_condition == "good"
    assert result.disagrees is False
    assert result.confidence == 0.88
    bc.complete_vision.assert_called_once()


def test_condition_disagreement_flags_human():
    """When assessed condition disagrees with stated, disagrees=True — never overwrites."""
    bc = _bedrock_returning("bedrock_condition_disagree.json")

    with patch("negagent.pipeline.condition._fetch_image", return_value=FAKE_IMAGE_BYTES):
        result = assess_condition(SAMPLE_LISTING, bedrock=bc)

    assert result.disagrees is True
    assert result.assessed_condition == "fair"
    # stated_condition on the listing is NOT modified
    assert SAMPLE_LISTING.stated_condition == "good"
