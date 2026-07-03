"""Loads strategies.json — the one file you edit to add, remove, or change strategies.

Nothing in this file or the rest of the bot needs to change when you add
a new strategy. Just edit config/strategies.json.
"""

import asyncio
import json
import os

STRATEGIES_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "strategies.json")

_sport_id_cache = None

# One lock, shared by every strategy runner in this process, so two
# strategies hitting balance 0 / target at the same moment can't both
# write strategies.json at once and corrupt it.
strategies_file_lock = asyncio.Lock()


async def disable_strategy(name, reason):
    """Sets enabled: false for one strategy in strategies.json, and
    leaves everything else in the file untouched. Safe to call from
    multiple strategies at once (uses strategies_file_lock).
    """
    async with strategies_file_lock:
        with open(STRATEGIES_FILE, encoding="utf-8") as f:
            data = json.load(f)

        found = False
        for s in data.get("strategies", []):
            if s.get("name") == name:
                s["enabled"] = False
                found = True
                break

        if not found:
            print(f"[{name}] ⚠️ Could not find this strategy in strategies.json to disable it.")
            return

        tmp_path = STRATEGIES_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, STRATEGIES_FILE)

        print(f"[{name}] 🛑 Disabled in strategies.json ({reason}).")


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
    """Returns the list of enabled, valid strategies from strategies.json.
    A strategy with a problem (e.g. its sport isn't offered right now)
    is skipped with a clear warning — it does not stop the other
    strategies from running.
    """
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

    valid = []
    for s in enabled:
        sport = s.get("sport_name") or (s.get("sport_names") or [None])[0]
        if sport not in sport_ids:
            print(f"[{s['name']}] ⚠️ SKIPPED — sport '{sport}' is not offered on Matchbook "
                  f"right now. Available: {sorted(sport_ids.keys())}")
            continue
        s["_sport_id"] = sport_ids[sport]

        if s.get("strategy_type") == "compound":
            missing = [k for k in ("compound_start", "compound_target", "min_back_odds", "max_back_odds")
                       if s.get(k) is None]
            if missing:
                print(f"[{s['name']}] ⚠️ SKIPPED — compound strategy missing: {', '.join(missing)}.")
                continue
        else:
            ladder = s.get("staking_plan", [])
            steps = s.get("staking_steps", len(ladder))
            if len(ladder) != steps:
                print(f"[{s['name']}] ⚠️ staking_steps ({steps}) doesn't match "
                      f"staking_plan length ({len(ladder)}). Using staking_plan length.")

        valid.append(s)

    return valid
