"""Finds a 'lay the opponent' opportunity in a Match Odds / Moneyline market.

Logic: if Home's back odds fall in the strategy's odds range, lay Away.
If Away's back odds fall in range, lay Home. Draw is never the trigger
or the lay target — only Home/Away (runner 0 and runner 1).

This is different from market_match_odds.py: that one backs the
selection that's in range. This one lays the OTHER selection.
"""


def find_opportunity(market, strategy):
    """Returns (runner_id, runner_name, odds) for the runner to LAY,
    or None if no trigger found. `odds` is the current best lay price
    available on the opposing runner — used to log/record the bet, the
    actual order is placed at that price.
    """
    runners = market.get("runners", [])
    if len(runners) < 2:
        return None

    home, away = runners[0], runners[1]

    home_back = _best_back_odds(home)
    away_back = _best_back_odds(away)

    trigger_runner = None
    opposing_runner = None

    if home_back is not None and strategy["min_back_odds"] <= home_back <= strategy["max_back_odds"]:
        trigger_runner = home
        opposing_runner = away
    elif away_back is not None and strategy["min_back_odds"] <= away_back <= strategy["max_back_odds"]:
        trigger_runner = away
        opposing_runner = home

    if trigger_runner is None or opposing_runner is None:
        return None

    lays = [p for p in opposing_runner.get("prices", []) if p.get("side") == "lay"]
    if not lays:
        return None

    best_lay = min(lays, key=lambda p: p.get("odds", float("inf")))
    lay_odds = best_lay.get("odds")
    size_available = best_lay.get("available-amount", best_lay.get("available_amount"))

    if lay_odds is None:
        return None

    min_liquidity = strategy.get("minimum_liquidity")
    if min_liquidity and size_available is not None and size_available < min_liquidity:
        return None

    return opposing_runner.get("id"), opposing_runner.get("name"), lay_odds


def _best_back_odds(runner):
    backs = [p for p in runner.get("prices", []) if p.get("side") == "back"]
    if not backs:
        return None
    best = min(backs, key=lambda p: p.get("odds", float("inf")))
    return best.get("odds")
