"""condition.py — Task 4.1: multimodal condition check via Bedrock vision.

assess_condition() downloads listing images, sends them + description to Bedrock
vision, and returns a ConditionAssessment. If the assessed condition disagrees with
the seller's stated condition, disagrees=True — the caller routes to HITL review.

Critical invariant: the listing's stated_condition is NEVER overwritten here.
The human decides; we only flag.
"""
from __future__ import annotations

import urllib.request
from typing import TYPE_CHECKING

from negagent.models import ConditionAssessment, Listing
from negagent.pipeline.comp_ingest import _parse_json

if TYPE_CHECKING:
    from negagent.clients.bedrock_client import BedrockClient

_SYSTEM = (
    "You are a product condition evaluator. "
    "Examine the provided listing images and description, then assess the item's condition. "
    "You MUST respond with ONLY a valid JSON object — no markdown, no prose, no explanation. "
    "Exact schema: "
    "{\"assessed_condition\": \"good\", \"confidence\": 0.85, \"disagrees\": false, \"rationale\": \"one sentence\"} "
    "assessed_condition must be one of: like_new, good, fair, poor. "
    "Set disagrees=true only if visual evidence clearly conflicts with the seller's stated condition."
)


def assess_condition(listing: Listing, bedrock: "BedrockClient") -> ConditionAssessment:
    """Download listing images and use Bedrock vision to assess condition.

    Never overwrites listing.stated_condition — returns a flag only.
    """
    content: list[dict] = []

    for url in listing.image_urls:
        try:
            image_bytes = _fetch_image(url)
            content.append({
                "image": {
                    "format": _guess_format(url),
                    "source": {"bytes": image_bytes},
                }
            })
        except Exception:
            pass  # skip unloadable images; vision still runs on remaining ones

    content.append({
        "text": (
            f"Seller's stated condition: {listing.stated_condition}\n"
            f"Title: {listing.title}\n"
            f"Description: {listing.desc}\n\n"
            "Assess the actual condition. Reply with ONLY the JSON object, nothing else."
        )
    })

    messages = [{"role": "user", "content": content}]
    raw = bedrock.complete_vision(messages, system=_SYSTEM)
    data = _parse_json(raw)

    return ConditionAssessment(
        assessed_condition=data.get("assessed_condition", listing.stated_condition),
        confidence=float(data.get("confidence", 0.0)),
        disagrees=bool(data.get("disagrees", False)),
        rationale=data.get("rationale", ""),
    )


def _fetch_image(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        return resp.read()


def _guess_format(url: str) -> str:
    lower = url.lower()
    for fmt in ("png", "gif", "webp"):
        if fmt in lower:
            return fmt
    return "jpeg"
