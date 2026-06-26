"""Loads strategies.json — the one file you edit to add, remove, or change strategies.

Nothing in this file or the rest of the bot needs to change when you add
a new strategy. Just edit config/strategies.json.
"""

import json
import os

STRATEGIES_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "strategies.json")

_sport_id_cache = None


def _get_sport_ids(client):
    """Asks Matchbook directly for the sport name -> id list. Cached after first call."""
    global _sport_id_cache
    if _sport_id_cache is not None:
        return _sport_id_cache

    nav = client.get_navigation()
    sports = nav if isinstance(nav, list) else (nav or {}).get("sports", [])

    lookup = {}
    for item in sports:
        for s in item.get("meta-tags", []):
            if s.get("type") == "SPORT":
                lookup[s["name"]] = str(s["id"])

    _sport_id_cache = lookup
    return lookup


def load_strategies(client):
    """Returns the list of enabled strategies from strategies.json."""
    if not os.path.isfile(STRATEGIES_FILE):
        raise FileNotFoundError(f"Missing config: {STRATEGIES_FILE}")

    with open(STRATEGIES_FILE, encoding="utf-8") as f:
        data = json.load(f)

    all_strategies = data.get("strategies", [])
    enabled = [s for s in all_strategies if s.get("enabled", True)]

    names = [s["name"] for s in enabled]
    if len(names) != len(set(names)):
        raise ValueError("Two enabled strategies have the same name. Names must be unique.")

    sport_ids = _get_sport_ids(client)

    for s in enabled:
        sport = s.get("sport_name") or (s.get("sport_names") or [None])[0]
        if sport not in sport_ids:
            raise ValueError(
                f"Strategy '{s['name']}': sport '{sport}' not found on Matchbook right now. "
                f"Available: {sorted(sport_ids.keys())}"
            )
        s["_sport_id"] = sport_ids[sport]

        ladder = s.get("staking_plan", [])
        steps = s.get("staking_steps", len(ladder))
        if len(ladder) != steps:
            print(f"[{s['name']}] ⚠️ staking_steps ({steps}) doesn't match "
                  f"staking_plan length ({len(ladder)}). Using staking_plan length.")

    return enabled
