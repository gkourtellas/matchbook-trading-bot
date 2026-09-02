"""Keeps a permanent record of every skipped bet, in its own small
database file (config/skips.db). Unlike logs/skipped.log, this never
rotates or gets deleted — safe to look back on months of skip history.
"""

import os
import re
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "skips.db")

_LEAGUE_PATTERN = re.compile(r"league '([^']+)' is not in this strategy's allowed leagues")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            strategy_name TEXT,
            event_name TEXT,
            reason TEXT,
            league TEXT
        )
    """)
    return conn


def record_skip(strategy_name, event_name, reason):
    """Call this every time a bet is skipped. Extracts the league name
    from the reason text automatically when it's a league-filter skip;
    league is NULL for every other skip reason.
    """
    league_match = _LEAGUE_PATTERN.search(reason)
    league = league_match.group(1) if league_match else None

    conn = _connect()
    conn.execute(
        "INSERT INTO skips (timestamp, strategy_name, event_name, reason, league) VALUES (?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), strategy_name, event_name, reason, league),
    )
    conn.commit()
    conn.close()
