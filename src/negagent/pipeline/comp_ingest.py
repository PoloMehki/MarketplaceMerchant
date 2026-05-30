"""comp_ingest.py — Tasks 2.2 / 2.3: query extraction + match-confidence scoring.

2.2  extract_query(listing, bedrock) -> StructuredQuery
     Bedrock turns a free-text FB title/description into a structured search query.
     Parses defensively: strips markdown fences and recovers JSON from prose.

2.3  score_comps(listing, comps, bedrock, threshold, repo) -> list[Comp]
     Bedrock scores each comp's relevance; drops below threshold; flags needs_human
     if too few pass.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from negagent.models import Comp, Listing

if TYPE_CHECKING:
    from negagent.clients.bedrock_client import BedrockClient

_MIN_SURVIVING_COMPS = 3


class NeedsHumanReview(Exception):
    """Raised when too few comps survive confidence filtering to trust the baseline."""

_EXTRACT_SYSTEM = (
    "You are a product search assistant. "
    "Given a Facebook Marketplace listing title and description, "
    "extract structured product information as JSON. "
    "Return ONLY valid JSON — no prose, no markdown fences. "
    "Schema: {brand, model, attributes (object of variant details), "
    "condition, search_query (a concise keyword string for e-commerce search)}."
)


@dataclass
class StructuredQuery:
    brand: str
    model: str
    search_query: str
    condition: str = ""
    attributes: dict = field(default_factory=dict)


def extract_query(listing: Listing, bedrock: "BedrockClient") -> StructuredQuery:
    """Use Bedrock to turn an FB listing into a structured search query."""
    user_content = (
        f"Title: {listing.title}\n"
        f"Description: {listing.desc}\n"
        f"Stated condition: {listing.stated_condition}"
    )
    messages = [{"role": "user", "content": [{"text": user_content}]}]
    raw = bedrock.complete(messages, system=_EXTRACT_SYSTEM)
    data = _parse_json(raw)
    return StructuredQuery(
        brand=data.get("brand", ""),
        model=data.get("model", ""),
        search_query=data.get("search_query", ""),
        condition=data.get("condition", ""),
        attributes=data.get("attributes", {}),
    )


_SCORE_SYSTEM = (
    "You are a product relevance judge. "
    "Given a target listing and a comparable product, score how well the comp "
    "matches the target on a scale of 0.0 to 1.0. "
    "Return ONLY valid JSON: {\"score\": <float>, \"rationale\": <string>}."
)


def score_comps(
    listing: Listing,
    comps: list[Comp],
    bedrock: "BedrockClient",
    threshold: float = 0.6,
    min_surviving: int = _MIN_SURVIVING_COMPS,
) -> list[Comp]:
    """Score each comp's relevance to the listing; drop weak matches.

    Raises NeedsHumanReview if fewer than min_surviving comps pass the threshold,
    so the caller can flag the negotiation state rather than proceeding on a bad
    price baseline.
    """
    passed: list[Comp] = []
    for comp in comps:
        user_content = (
            f"Target listing: {listing.title} — {listing.desc}\n"
            f"Comp: {comp.title} (${comp.price}, {comp.condition})"
        )
        messages = [{"role": "user", "content": [{"text": user_content}]}]
        raw = bedrock.complete(messages, system=_SCORE_SYSTEM)
        data = _parse_json(raw)
        score = float(data.get("score", 0.0))
        if score >= threshold:
            comp.match_confidence = score
            comp.matched = True
            passed.append(comp)

    if len(passed) < min_surviving:
        raise NeedsHumanReview(
            f"Only {len(passed)} comp(s) passed threshold {threshold} "
            f"(need {min_surviving}). Flag for human review."
        )
    return passed


def _parse_json(text: str) -> dict:
    """Extract the first JSON object from text, tolerating markdown fences and prose."""
    # strip ```json ... ``` fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # find the first balanced {...} block
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start : i + 1])
    raise ValueError(f"No JSON object found in Bedrock response: {text!r}")
