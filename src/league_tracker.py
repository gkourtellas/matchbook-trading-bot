"""Keeps a running, de-duplicated list of leagues/competitions seen for
each sport, one file per sport, so they can be used later as filters
when setting up strategies.

Saved to config/leagues/<sport>.json — a simple list of names.

Matchbook's event data doesn't have one single confirmed field name for
this in our testing, so this checks several likely spots and saves
whatever it finds. If nothing is found, it saves nothing — silent,
doesn't affect betting.
"""

import os
import json

LEAGUES_DIR = os.path.join(os.path.dirname(__file__), "..", "config", "leagues")


def _safe_filename(sport_name):
    return "".join(c if c.isalnum() else "_" for c in sport_name.strip()) + ".json"


def _extract_league_name(event):
    """Tries a few likely field names/locations for the league/competition.
    Returns None if nothing usable is found.
    """
    for key in ("category", "competition", "competition-name", "tournament", "league", "league-name"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            name = value.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def record_league(sport_name, event):
    """Call this once per placed bet. Adds the event's league to that
    sport's file if it's new. Safe to call even if nothing is found.
    """
    league = _extract_league_name(event)
    if not league:
        return

    os.makedirs(LEAGUES_DIR, exist_ok=True)
    path = os.path.join(LEAGUES_DIR, _safe_filename(sport_name))

    existing = []
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    if league not in existing:
        existing.append(league)
        existing.sort()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save league list for {sport_name}: {e}")
