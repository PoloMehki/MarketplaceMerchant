"""negotiation_repo.py — Task 1.2: CRUD for negotiation state.

Provides create / get / update_state / append_turn / set_best_price over the
``negotiations`` table. Reads return plain dicts whose keys mirror the
NegotiationState / OfferTurn field shapes from the spec (models.py, Task 1.1,
Dev A). Kept model-agnostic on purpose: this lane must not block on Dev A's
models. Once models.py lands, callers may wrap results, e.g.
``NegotiationState(**repo.get(listing_id))``.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .db import connect, init_db

# Valid NegotiationState.status values (spec, Task 1.1).
STATUSES = frozenset({"active", "accepted", "walked", "sold", "needs_human"})

# Sentinel so update_state can tell "leave current_offer unchanged" apart from
# "set current_offer to None".
_UNSET: Any = object()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class NegotiationRepo:
    """Thin repository over a single SQLite connection (single-writer, v1)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, path: "str | Path") -> "NegotiationRepo":
        """Open (and initialize) a repo at ``path`` (or ``":memory:"``)."""
        conn = connect(path)
        init_db(conn)
        return cls(conn)

    # --- writes ---

    def create(
        self,
        listing_id: str,
        *,
        status: str = "active",
        current_offer: Optional[float] = None,
        best_price_found: Optional[float] = None,
    ) -> dict:
        """Insert a new negotiation row. Raises ValueError if it already exists."""
        self._check_status(status)
        try:
            self._conn.execute(
                "INSERT INTO negotiations "
                "(listing_id, status, current_offer, best_price_found, turns) "
                "VALUES (?, ?, ?, ?, '[]')",
                (listing_id, status, current_offer, best_price_found),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"negotiation already exists for listing_id={listing_id!r}"
            ) from exc
        return self._require(listing_id)

    def update_state(
        self, listing_id: str, status: str, *, current_offer: Any = _UNSET
    ) -> dict:
        """Update status (and optionally current_offer) for an existing row."""
        self._check_status(status)
        self._require(listing_id)
        if current_offer is _UNSET:
            self._conn.execute(
                "UPDATE negotiations SET status = ? WHERE listing_id = ?",
                (status, listing_id),
            )
        else:
            self._conn.execute(
                "UPDATE negotiations SET status = ?, current_offer = ? "
                "WHERE listing_id = ?",
                (status, current_offer, listing_id),
            )
        self._conn.commit()
        return self._require(listing_id)

    def append_turn(
        self,
        listing_id: str,
        role: str,
        amount: Optional[float],
        message: str,
        ts: Optional[str] = None,
    ) -> dict:
        """Append an OfferTurn-shaped entry to the JSON turns column."""
        record = self._require(listing_id)
        turn = {
            "role": role,
            "amount": amount,
            "message": message,
            "ts": ts or _now_iso(),
        }
        turns = record["turns"]
        turns.append(turn)
        self._conn.execute(
            "UPDATE negotiations SET turns = ? WHERE listing_id = ?",
            (json.dumps(turns), listing_id),
        )
        self._conn.commit()
        return self._require(listing_id)

    def set_best_price(self, listing_id: str, price: float) -> dict:
        """Record ``price`` as best_price_found only if it is a new minimum."""
        record = self._require(listing_id)
        best = record["best_price_found"]
        if best is None or price < best:
            self._conn.execute(
                "UPDATE negotiations SET best_price_found = ? WHERE listing_id = ?",
                (price, listing_id),
            )
            self._conn.commit()
        return self._require(listing_id)

    # --- reads ---

    def get(self, listing_id: str) -> Optional[dict]:
        """Return the negotiation as a dict, or None if it does not exist."""
        row = self._conn.execute(
            "SELECT listing_id, status, current_offer, best_price_found, turns "
            "FROM negotiations WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "listing_id": row["listing_id"],
            "status": row["status"],
            "current_offer": row["current_offer"],
            "best_price_found": row["best_price_found"],
            "turns": json.loads(row["turns"]),
        }

    def close(self) -> None:
        self._conn.close()

    # --- internals ---

    def _require(self, listing_id: str) -> dict:
        record = self.get(listing_id)
        if record is None:
            raise KeyError(f"no negotiation for listing_id={listing_id!r}")
        return record

    @staticmethod
    def _check_status(status: str) -> None:
        if status not in STATUSES:
            raise ValueError(
                f"invalid status {status!r}; expected one of {sorted(STATUSES)}"
            )
