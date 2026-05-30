"""Task 1.1: test_models_roundtrip, test_price_mode_validation."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from negagent.models import (
    Comp,
    ConditionAssessment,
    Listing,
    NegotiationState,
    OfferTurn,
    PriceTargets,
    TargetSpec,
)


def _sample_state() -> NegotiationState:
    return NegotiationState(
        listing_id="fb123",
        status="active",
        current_offer=180.0,
        best_price_found=175.0,
        turns=[
            OfferTurn(
                role="buyer",
                amount=180.0,
                message="Would you take $180?",
                ts=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
            ),
            OfferTurn(
                role="seller",
                amount=200.0,
                message="I can do $200.",
                ts=datetime(2026, 5, 29, 12, 5, tzinfo=timezone.utc),
            ),
        ],
    )


def test_models_roundtrip():
    """Every model serializes to JSON and deserializes back to an equal object."""
    samples = [
        TargetSpec(
            query="iphone 13",
            category="electronics",
            acceptable_conditions=["good", "like_new"],
            price_mode="below_median_pct",
            threshold_value=0.15,
            time_window_minutes=120,
        ),
        Comp(
            source="amazon",
            title="iPhone 13 128GB",
            price=420.0,
            condition="used",
            url="https://example.com/a",
            matched=True,
            match_confidence=0.92,
        ),
        Listing(
            fb_id="fb123",
            title="iPhone 13",
            desc="Lightly used, 128GB",
            price=350.0,
            stated_condition="good",
            image_urls=["https://img/1.jpg", "https://img/2.jpg"],
            seller="Jane D.",
            url="https://facebook.com/marketplace/item/123",
        ),
        ConditionAssessment(
            assessed_condition="fair",
            confidence=0.8,
            disagrees=True,
            rationale="Visible scratches not mentioned in listing.",
        ),
        PriceTargets(good_price=300.0, anchor=260.0, target=300.0, walkaway=340.0),
        _sample_state(),
    ]
    for obj in samples:
        restored = type(obj).model_validate_json(obj.model_dump_json())
        assert restored == obj


def test_price_mode_validation():
    """TargetSpec rejects an unknown price_mode."""
    with pytest.raises(ValidationError):
        TargetSpec(
            query="iphone 13",
            category="electronics",
            acceptable_conditions=["good"],
            price_mode="totally_made_up_mode",
            threshold_value=0.15,
            time_window_minutes=120,
        )


def test_negotiation_status_validation():
    """NegotiationState rejects an unknown status enum."""
    with pytest.raises(ValidationError):
        NegotiationState(listing_id="fb123", status="bogus_status")
