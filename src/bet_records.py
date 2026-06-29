"""Keeps a permanent record of every bet, in one small database file
(config/bets.db). Used for reporting later — profit, win rate, how
often each step gets hit, etc.
"""

import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "bets.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name TEXT,
            event_name TEXT,
            selection_name TEXT,
            odds REAL,
            stake REAL,
            step INTEGER,
            placed_at TEXT,
            settled_at TEXT,
            result TEXT,
            profit REAL,
            result_type TEXT,
            league TEXT
        )
    """)
    # Older databases won't have these columns yet — add if missing.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bets)").fetchall()]
    if "result_type" not in cols:
        conn.execute("ALTER TABLE bets ADD COLUMN result_type TEXT")
    if "league" not in cols:
        conn.execute("ALTER TABLE bets ADD COLUMN league TEXT")
    return conn


def record_bet_placed(strategy_name, event_name, selection_name, odds, stake, step, placed_at, league=None):
    """Call this the moment a bet is placed. Returns the row id."""
    conn = _connect()
    cur = conn.execute(
        """INSERT INTO bets (strategy_name, event_name, selection_name, odds, stake, step, placed_at, league)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (strategy_name, event_name, selection_name, odds, stake, step, placed_at.isoformat(), league),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def record_bet_settled(row_id, result, odds, stake):
    """Call this once a bet's result (won/lost) is known."""
    profit = round(stake * (odds - 1), 4) if result == "won" else -stake
    conn = _connect()
    conn.execute(
        "UPDATE bets SET result = ?, profit = ?, settled_at = ?, result_type = 'normal' WHERE id = ?",
        (result, profit, datetime.utcnow().isoformat(), row_id),
    )
    conn.commit()
    conn.close()


def record_bet_cashed_out(row_id, locked_in_profit):
    """Call this when a bet is closed early via a cash-out (hedge) lay bet,
    instead of record_bet_settled. Keeps cash-outs distinguishable from
    normal wins/losses in reports.
    """
    conn = _connect()
    conn.execute(
        "UPDATE bets SET result = 'won', profit = ?, settled_at = ?, result_type = 'cashed_out' WHERE id = ?",
        (locked_in_profit, datetime.utcnow().isoformat(), row_id),
    )
    conn.commit()
    conn.close()
