"""db.py — Task 1.2: SQLite connection + schema creation.

Single-writer, local-file (or in-memory) store. The only table is
``negotiations``; per-negotiation offer history is kept in a JSON ``turns``
column (v1 — no separate turns table). Pure Dev B: no dependency on models.py
(Task 1.1) so this lane never blocks on Dev A.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

# Column shapes mirror NegotiationState / OfferTurn (models.py, Task 1.1).
SCHEMA = """
CREATE TABLE IF NOT EXISTS negotiations (
    listing_id        TEXT PRIMARY KEY,
    status            TEXT NOT NULL,
    current_offer     REAL,
    best_price_found  REAL,
    turns             TEXT NOT NULL DEFAULT '[]'
);
"""


def connect(path: "str | Path") -> sqlite3.Connection:
    """Open a SQLite connection with rows accessible by column name.

    ``path`` may be a filesystem path or the special string ``":memory:"``.
    """
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the schema if it does not already exist."""
    conn.executescript(SCHEMA)
    conn.commit()
