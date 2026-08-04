"""Loads strategies.json — the one file you edit to add, remove, or change strategies.

Nothing in this file or the rest of the bot needs to change when you add
a new strategy. Just edit config/strategies.json.

Also loads config/league_categories.json, which lets strategies say
"only bet these league categories" instead of listing leagues one by one.
Categories are live-linked: edit the category on the dashboard and every
strategy using it picks up the change on next restart.
"""

import asyncio
import json
import os

STRATEGIES_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "strategies.json")
CATEGORIES_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "league_categories.json")

_sport_id_cache = None

# One lock, shared by every strategy runner in this process, so two
# strategies hitting balance 0 / target at the same moment can't both
# write strategies.json at once and corrupt it.
strategies_file_lock = asyncio.Lock()


def load_categories():
    """Returns the category -> [league names] dict from league_categories.json.
    Empty dict if the file doesn't exist yet.
    """
    if not os.path.isfile(CATEGORIES_FILE):
        return {}
    with open(CATEGORIES_FILE, encoding="utf-8") as f:
        return json.load(f)


def resolve_included_leagues(strategy):
    """Turns a strategy's included_categories (plus included_leagues as a
    fallback for one-off leagues not in any category) into one flat set
    of league names this strategy is allowed to bet on.

    Returns None if the strategy has no categories and no individual
    leagues set — meaning "no filter, bet any league" (old behavior).
    """
    included_categories = strategy.get("included_categories") or []
    included_leagues = strategy.get("included_leagues") or []

    if not included_categories and not included_leagues:
        return None

    categories = load_categories()
    allowed = set(included_leagues)
    for cat_name in included_categories:
        allowed.update(categories.get(cat_name, []))

    return allowed


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
        sport_configs = s.get("sport_configs")

        if sport_configs:
            # Multi-sport strategy: resolve a sport id for each row.
            missing = []
            for row in sport_configs:
                row_sport = row.get("sport_name")
                if row_sport in sport_ids:
                    row["_sport_id"] = sport_ids[row_sport]
                else:
                    missing.append(row_sport)
            if missing:
                print(f"[{s['name']}] ⚠️ Some sports not offered right now, skipping those rows: {missing}")
            if not any(row.get("_sport_id") for row in sport_configs):
                print(f"[{s['name']}] ⚠️ SKIPPED — none of its sports are offered on Matchbook right now.")
                continue
        else:
            sport = s.get("sport_name") or (s.get("sport_names") or [None])[0]
            if sport not in sport_ids:
                print(f"[{s['name']}] ⚠️ SKIPPED — sport '{sport}' is not offered on Matchbook "
                      f"right now. Available: {sorted(sport_ids.keys())}")
                continue
            s["_sport_id"] = sport_ids[sport]

        # Live-linked league filter: resolved fresh every load, so
        # editing a category on the dashboard applies on next restart
        # without touching strategies.json.
        s["_allowed_leagues"] = resolve_included_leagues(s)

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
