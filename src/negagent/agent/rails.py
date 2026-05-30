"""rails.py — Tasks 6.1 + 6.3: negotiation system prompt, numeric guardrails,
and the HITL approval gate.

Builds the Bedrock system prompt that constrains the negotiation agent to five
hard rails, provides code-level numeric guardrails (validate_offer /
validate_concession) enforced independently of the prompt, and implements
HITLApprovalGate — the BeforeToolCallEvent hook that intercepts send-type
Playwright tool calls and requires explicit human approval before they fire.

Model-agnostic by design: the builders duck-type their inputs (PriceTargets,
Listing, Comp from models.py, Task 1.1, Dev A) via attribute access, so this
lane does not block on Dev A's models. Any object exposing the documented
attributes works — real pydantic models or test stand-ins.

Prompt text is intentionally ASCII-only so it renders/encodes cleanly on a
Windows (cp1252) console and in any logging sink.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

# Playwright tool names that write content to the page (message composer).
# Navigate / snapshot / screenshot are reads and are never intercepted.
SEND_TOOLS: frozenset[str] = frozenset(
    {"browser_type", "browser_fill_form", "browser_press_key"}
)

# How many comparable listings to cite in the prompt (keep it tight).
_MAX_COMPS_IN_PROMPT = 8


def validate_offer(amount: float, walkaway: float) -> bool:
    """Return True if ``amount`` is allowed (at or below the walk-away ceiling).

    Code-level guardrail (Rail 1): any drafted offer above ``walkaway`` is
    rejected here, before it can reach the send gate -- independent of whatever
    the model produced.
    """
    return amount <= walkaway


def validate_concession(
    previous_offer: float, new_offer: float, max_concession_per_turn: float
) -> bool:
    """Return True if moving from ``previous_offer`` to ``new_offer`` is allowed.

    Code-level guardrail (Rail 3): the buyer must not raise their offer by more
    than ``max_concession_per_turn`` in a single step. Holding or lowering the
    offer is always allowed.
    """
    return (new_offer - previous_offer) <= max_concession_per_turn + 1e-9


def default_max_concession(targets) -> float:
    """A heuristic per-turn concession cap (~20% of the anchor->ceiling room).

    Callers may override with an explicit value; this just gives the prompt a
    concrete Rail 3 number when none is supplied.
    """
    room = max(float(targets.walkaway) - float(targets.anchor), 0.0)
    return round(max(room * 0.2, 1.0), 2)


def _format_comps(comps: Iterable) -> str:
    lines = []
    for c in comps:
        if not getattr(c, "matched", True):
            continue
        lines.append(
            f"  - {c.title}: ${float(c.price):.0f} "
            f"({getattr(c, 'condition', 'unknown')}, via {getattr(c, 'source', 'comp')})"
        )
        if len(lines) >= _MAX_COMPS_IN_PROMPT:
            break
    return "\n".join(lines) if lines else "  (no comparable listings available)"


def build_system_prompt(
    targets, listing, comps, *, max_concession_per_turn: Optional[float] = None
) -> str:
    """Build the negotiation system prompt encoding all five hard rails."""
    cap = (
        default_max_concession(targets)
        if max_concession_per_turn is None
        else float(max_concession_per_turn)
    )
    comps_block = _format_comps(comps)

    return f"""You are a buyer's negotiation assistant. You negotiate, on the buyer's behalf, to purchase ONE specific second-hand item from its seller over Facebook Marketplace Messenger. You only draft messages; a human reviews and approves every message before it is sent.

ITEM
  Title: {listing.title}
  Seller's asking price: ${float(listing.price):.0f}
  Stated condition: {getattr(listing, "stated_condition", "unknown")}
  Listing: {getattr(listing, "url", "n/a")}

COMPARABLE ACTIVE LISTINGS (evidence you may cite to justify offers)
{comps_block}

YOUR PRICE TARGETS - INTERNAL, NEVER SHARE (see Rail 2)
  Fair value (good price): ${float(targets.good_price):.0f}
  Opening offer (anchor):  ${float(targets.anchor):.0f}
  Settle target:           ${float(targets.target):.0f}
  Walk-away ceiling:       ${float(targets.walkaway):.0f}

HARD RAILS - you must never break these:
  1. Never offer, accept, or imply any price above your walk-away ceiling of ${float(targets.walkaway):.0f}.
  2. Never disclose your maximum, budget, walk-away, or any of these internal targets to the seller. They are yours alone.
  3. Concede slowly: raise your offer by no more than ${cap:.0f} between one of your offers and the next.
  4. If the seller will not come down to your settle target of ${float(targets.target):.0f} within these rails, do NOT accept a higher price on your own; present the best price you achieved to the buyer for a human decision.
  5. Be courteous and respectful, and justify your offers with the comparable-listing evidence above, never by revealing your limits.

Within these rails you own the tone and tactics: open near your anchor, cite comps, concede slowly toward your target, and stay friendly throughout."""


@dataclass(frozen=True)
class Rails:
    """Bundle of the built prompt + numeric guardrails for one negotiation.

    Convenience for Stage 6: hand a single ``Rails`` to the agent wiring (6.2)
    and the send gate (6.3). ``validate_offer(amount)`` is the single-argument
    ceiling check the gate calls before approving a send.
    """

    system_prompt: str
    good_price: float
    anchor: float
    target: float
    walkaway: float
    max_concession_per_turn: float

    def validate_offer(self, amount: float) -> bool:
        # Delegates to the module-level pure guardrail, bound to this ceiling.
        return validate_offer(amount, self.walkaway)

    def validate_concession(self, previous_offer: float, new_offer: float) -> bool:
        return validate_concession(
            previous_offer, new_offer, self.max_concession_per_turn
        )


def build_rails(
    targets, listing, comps, *, max_concession_per_turn: Optional[float] = None
) -> Rails:
    """Build the full Rails bundle (prompt + numeric guardrails) for a setup."""
    cap = (
        default_max_concession(targets)
        if max_concession_per_turn is None
        else float(max_concession_per_turn)
    )
    prompt = build_system_prompt(targets, listing, comps, max_concession_per_turn=cap)
    return Rails(
        system_prompt=prompt,
        good_price=float(targets.good_price),
        anchor=float(targets.anchor),
        target=float(targets.target),
        walkaway=float(targets.walkaway),
        max_concession_per_turn=cap,
    )


class HITLApprovalGate(HookProvider):
    """BeforeToolCallEvent hook that gates send-type Playwright tool calls.

    Read-only tools (navigate, snapshot, screenshot, etc.) pass through without
    interruption. Any tool in SEND_TOOLS is intercepted: ``approval_fn`` is
    called with (tool_name, tool_input) and must return True to allow the call.
    On False, ``event.cancel_tool`` is set and the agent is asked to revise.

    This is the single most important safety/ToS control: the agent only drafts;
    a human authorizes every send.

    Args:
        approval_fn: Callable(tool_name: str, tool_input: dict) -> bool.
            The CLI wires a terminal prompt here; tests pass a lambda.
    """

    def __init__(self, approval_fn: Callable[[str, dict], bool]) -> None:
        self._approval_fn = approval_fn

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self._check_send)

    def _check_send(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use["name"] not in SEND_TOOLS:
            return
        approved = self._approval_fn(
            event.tool_use["name"],
            event.tool_use.get("input", {}),
        )
        if not approved:
            event.cancel_tool = "Human rejected the send. Revise the message and try again."
