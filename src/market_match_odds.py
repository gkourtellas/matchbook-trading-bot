"""Finds a betting opportunity in a 'Match Odds' or 'Moneyline' market
(both are simple win/lose markets — same logic, different name per sport).
Also handles 'Both Teams To Score' — same structure (a list of runners
with back/lay prices), just with "Yes"/"No" runners instead of team names.

Filters added:
- min_field_size: skip market if fewer runners than this (team sports too)
- spread_cap_percent: skip runner if (lay-back)/back * 100 > cap (thin market)
- btts_direction: for BTTS markets only — "Yes" or "No" to only consider
  that side. Leave unset/empty to allow either (old behavior).
- runner_side (2026-09-21): for Match Odds / Moneyline only — "home" or
  "away" to only consider that team. Leave unset/empty to allow either
  (old behavior). Draw is never Home or Away. Home = first team listed,
  Away = second team listed (same order market_lay_opponent.py uses).

FIX (2026-09-06): strategy.get("btts_direction", "") only falls back to
"" when the key is MISSING. Strategies saved with btts_direction: null
(key present, value None) got str(None) = "None" -> "none", which is
truthy, so EVERY runner got skipped (no runner is named "none"). This
silently killed Match Odds / Moneyline / Win strategies that don't use
BTTS at all. Now treats None the same as missing.
"""


def _pick_side_runner(runners, runner_side):
    """Returns the one runner allowed by runner_side ("home"/"away"),
    or None if it can't be worked out. Draw is skipped by name.
    """
    teams = [r for r in runners if (r.get("name") or "").strip().lower() != "draw"]
    if len(teams) < 2:
        return None
    return teams[0] if runner_side == "home" else teams[1]


def find_opportunity(market, strategy):
    """Returns (runner_id, runner_name, odds) if this market has a bet
    worth placing, otherwise None.
    """
    runners = market.get("runners", [])

    min_field_size = strategy.get("min_field_size")
    if min_field_size and len(runners) < min_field_size:
        return None

    spread_cap = strategy.get("spread_cap_percent")
    raw_btts_direction = strategy.get("btts_direction")
    wanted_direction = str(raw_btts_direction).strip().lower() if raw_btts_direction else ""

    runner_side = str(strategy.get("runner_side") or "").strip().lower()
    side_runner = None
    if runner_side in ("home", "away"):
        side_runner = _pick_side_runner(runners, runner_side)
        if side_runner is None:
            return None

    for runner in runners:
        runner_name = runner.get("name") or ""

        if side_runner is not None and runner is not side_runner:
            continue

        if wanted_direction and wanted_direction != runner_name.strip().lower():
            continue

        prices = runner.get("prices", [])
        backs = [p for p in prices if p.get("side") == "back"]
        if not backs:
            continue

        best = min(backs, key=lambda p: p.get("odds", float("inf")))
        odds = best.get("odds")
        size_available = best.get("available-amount", best.get("available_amount"))

        if odds is None:
            continue
        if not (strategy["min_back_odds"] <= odds <= strategy["max_back_odds"]):
            continue

        min_liquidity = strategy.get("minimum_liquidity")
        if min_liquidity and size_available is not None and size_available < min_liquidity:
            continue

        if spread_cap:
            lays = [p for p in prices if p.get("side") == "lay"]
            if not lays:
                continue
            best_lay = min(lays, key=lambda p: p.get("odds", float("inf")))
            lay_odds = best_lay.get("odds")
            if lay_odds is None:
                continue
            spread_pct = (lay_odds - odds) / odds * 100
            if spread_pct > spread_cap:
                continue

        return runner.get("id"), runner.get("name"), odds

    return None
