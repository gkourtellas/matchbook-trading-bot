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
            profit REAL
        )
    """)
    return conn


def record_bet_placed(strategy_name, event_name, selection_name, odds, stake, step, placed_at):
    """Call this the moment a bet is placed. Returns the row id."""
    conn = _connect()
    cur = conn.execute(
        """INSERT INTO bets (strategy_name, event_name, selection_name, odds, stake, step, placed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (strategy_name, event_name, selection_name, odds, stake, step, placed_at.isoformat()),
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
        "UPDATE bets SET result = ?, profit = ?, settled_at = ? WHERE id = ?",
        (result, profit, datetime.utcnow().isoformat(), row_id),
    )
    conn.commit()
    conn.close()
