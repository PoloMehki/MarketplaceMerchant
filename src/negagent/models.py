"""models.py — Task 1.1: pydantic data models.

Shared foundation for both lanes. Dev A owns the initial shapes; both lanes
append their own fields here (append-only, coordinate before editing).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

PriceMode = Literal["budget", "below_median_pct", "below_avg_pct"]
NegotiationStatus = Literal["active", "accepted", "walked", "sold", "needs_human"]
TurnRole = Literal["buyer", "seller"]


class TargetSpec(BaseModel):
    """What the buyer is looking for and how to price it."""

    query: str
    category: str
    acceptable_conditions: list[str] = Field(default_factory=list)
    price_mode: PriceMode
    threshold_value: float
    time_window_minutes: int


class Comp(BaseModel):
    """An active e-commerce comparable listing used to ground a fair price."""

    source: str
    title: str
    price: float
    condition: str
    url: str
    matched: bool = False
    match_confidence: float = 0.0


class Listing(BaseModel):
    """A Facebook Marketplace listing scraped for the target item."""

    fb_id: str
    title: str
    desc: str
    price: float
    stated_condition: str
    image_urls: list[str] = Field(default_factory=list)
    seller: str
    url: str


class ConditionAssessment(BaseModel):
    """Result of the multimodal condition check — a flag, never an overwrite."""

    assessed_condition: str
    confidence: float
    disagrees: bool
    rationale: str


class PriceTargets(BaseModel):
    """The four negotiation numbers derived from comps."""

    good_price: float
    anchor: float
    target: float
    walkaway: float


class OfferTurn(BaseModel):
    """A single turn in the negotiation transcript."""

    role: TurnRole
    amount: Optional[float] = None
    message: str
    ts: datetime


class NegotiationState(BaseModel):
    """Persisted state for a single listing's negotiation."""

    listing_id: str
    status: NegotiationStatus = "active"
    current_offer: Optional[float] = None
    best_price_found: Optional[float] = None
    turns: list[OfferTurn] = Field(default_factory=list)
