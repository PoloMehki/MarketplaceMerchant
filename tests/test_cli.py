"""Task 8.1: test_cli_happy_path_end_to_end, test_cli_stops_on_match_flag,
test_cli_stops_on_condition_flag.

All externals (Apify, Bedrock, Box, MCP, Agent) are mocked. The repo uses an
in-memory SQLite DB. HITL functions are simple lambdas.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from negagent.cli import run_pipeline
from negagent.config import AppConfig
from negagent.models import (
    Comp,
    ConditionAssessment,
    Listing,
    PriceTargets,
    TargetSpec,
)
from negagent.pipeline.comp_ingest import NeedsHumanReview
from negagent.store.negotiation_repo import NegotiationRepo


# ── shared test data ─────────────────────────────────────────────────────────

def _spec() -> TargetSpec:
    return TargetSpec(
        query="Herman Miller Aeron",
        category="furniture",
        acceptable_conditions=["good"],
        price_mode="below_median_pct",
        threshold_value=0.15,
        time_window_minutes=60,
    )


def _cfg() -> AppConfig:
    return AppConfig(
        aws_region="us-west-2",
        bedrock_model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        apify_token="tok",
        apify_ecommerce_actor_id="apify/ecommerce",
        apify_fb_actor_id="apify/fb",
        box_client_id="bid",
        box_client_secret="bsec",
    )


def _listing() -> Listing:
    return Listing(
        fb_id="fb123",
        title="Herman Miller Aeron Size B",
        desc="Barely used, great condition.",
        price=600.0,
        stated_condition="good",
        image_urls=[],
        seller="Mehki Polo",
        url="https://www.facebook.com/marketplace/item/123",
    )


def _comps() -> list[Comp]:
    return [
        Comp(source="ebay", title="Aeron B", price=550.0, condition="good",
             url="u1", matched=True, match_confidence=0.92),
        Comp(source="ebay", title="Aeron B", price=520.0, condition="good",
             url="u2", matched=True, match_confidence=0.88),
        Comp(source="ebay", title="Aeron B", price=580.0, condition="good",
             url="u3", matched=True, match_confidence=0.85),
    ]


def _targets() -> PriceTargets:
    return PriceTargets(good_price=522.5, anchor=426.08, target=473.42, walkaway=550.0)


def _assessment(*, disagrees: bool = False) -> ConditionAssessment:
    return ConditionAssessment(
        assessed_condition="good",
        confidence=0.9,
        disagrees=disagrees,
        rationale="Looks as described.",
    )


def _mock_apify() -> MagicMock:
    client = MagicMock()
    client.run_ecommerce_comps.return_value = [
        {"source": "ebay", "title": "Aeron B", "price": 550.0, "condition": "good", "url": "u1"},
        {"source": "ebay", "title": "Aeron B", "price": 520.0, "condition": "good", "url": "u2"},
        {"source": "ebay", "title": "Aeron B", "price": 580.0, "condition": "good", "url": "u3"},
    ]
    return client


def _mock_mcp() -> MagicMock:
    m = MagicMock()
    m.stop = MagicMock()
    return m


@pytest.fixture
def repo():
    r = NegotiationRepo.open(":memory:")
    yield r
    r.close()


# ── tests ────────────────────────────────────────────────────────────────────

def test_cli_happy_path_end_to_end(repo):
    mock_agent = MagicMock(return_value="negotiation done")
    mock_mcp = _mock_mcp()
    mock_box = MagicMock()
    mock_query = SimpleNamespace(search_query="Herman Miller Aeron")

    with patch("negagent.cli.ingest_listings", return_value=[_listing()]), \
         patch("negagent.cli.extract_query", return_value=mock_query), \
         patch("negagent.cli.score_comps", return_value=_comps()), \
         patch("negagent.cli.assess_condition", return_value=_assessment()), \
         patch("negagent.cli.compute_targets", return_value=_targets()), \
         patch("negagent.cli.build_bedrock_model", return_value=MagicMock()), \
         patch("negagent.cli.build_agent", return_value=mock_agent):

        result = run_pipeline(
            _spec(), _cfg(), repo,
            apify_client=_mock_apify(),
            bedrock_client=MagicMock(),
            box_client=mock_box,
            mcp_client=mock_mcp,
            approval_fn=lambda name, inp: True,
            hitl_fn=lambda prompt: True,
        )

    # pipeline completed and wrote a negotiation record
    assert result is not None
    assert result["listing_id"] == "fb123"
    assert result["status"] == "active"

    # agent was invoked twice: once for the warmup navigate, once for the main instruction
    assert mock_agent.call_count == 2
    warmup_call = mock_agent.call_args_list[0][0][0]
    assert "facebook.com/marketplace" in warmup_call
    instruction = mock_agent.call_args_list[1][0][0]
    assert "browser_fill_form" in instruction
    assert "already loaded" in instruction

    # MCP was cleaned up
    mock_mcp.stop.assert_called_once_with(None, None, None)

    # Box archival was triggered
    mock_box.archive_negotiation.assert_called_once()


def test_cli_stops_on_match_flag(repo):
    mock_agent = MagicMock()
    mock_query = SimpleNamespace(search_query="aeron")

    with patch("negagent.cli.ingest_listings", return_value=[_listing()]), \
         patch("negagent.cli.extract_query", return_value=mock_query), \
         patch("negagent.cli.score_comps",
               side_effect=NeedsHumanReview("only 1 comp passed threshold")), \
         patch("negagent.cli.build_agent", return_value=mock_agent):

        result = run_pipeline(
            _spec(), _cfg(), repo,
            apify_client=_mock_apify(),
            bedrock_client=MagicMock(),
            box_client=MagicMock(),
            mcp_client=_mock_mcp(),
            approval_fn=lambda name, inp: True,
            hitl_fn=lambda prompt: False,   # operator aborts
        )

    assert result == {"status": "needs_human", "reason": "match_flag"}
    mock_agent.assert_not_called()


def test_cli_stops_on_condition_flag(repo):
    mock_agent = MagicMock()
    mock_query = SimpleNamespace(search_query="aeron")

    with patch("negagent.cli.ingest_listings", return_value=[_listing()]), \
         patch("negagent.cli.extract_query", return_value=mock_query), \
         patch("negagent.cli.score_comps", return_value=_comps()), \
         patch("negagent.cli.assess_condition",
               return_value=_assessment(disagrees=True)), \
         patch("negagent.cli.build_agent", return_value=mock_agent):

        result = run_pipeline(
            _spec(), _cfg(), repo,
            apify_client=_mock_apify(),
            bedrock_client=MagicMock(),
            box_client=MagicMock(),
            mcp_client=_mock_mcp(),
            approval_fn=lambda name, inp: True,
            hitl_fn=lambda prompt: False,   # operator aborts
        )

    assert result == {"status": "needs_human", "reason": "condition_flag"}
    mock_agent.assert_not_called()
