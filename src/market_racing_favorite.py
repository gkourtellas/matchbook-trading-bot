"""Finds a bet in a horse/greyhound 'Win' market.

Unlike market_match_odds.py (which backs whichever runner is in range),
this one always looks at the FAVORITE specifically — the runner with the
shortest (lowest) back odds — and only bets it if:

  - the race has at least `min_field_size` runners (default 6)
  - the favorite's best back odds fall within min_back_odds/max_back_odds

Config fields used from the strategy:
  min_field_size   (optional, default 6)
  min_back_odds
  max_back_odds
  minimum_liquidity (optional)
"""


def find_opportunity(market, strategy):
    """Returns (runner_id, runner_name, odds) for the favorite, or None
    if the race doesn't qualify.
    """
    runners = market.get("runners", [])
    min_field_size = strategy.get("min_field_size", 6)

    if len(runners) < min_field_size:
        return None

    candidates = []
    for runner in runners:
        backs = [p for p in runner.get("prices", []) if p.get("side") == "back"]
        if not backs:
            continue
        best = min(backs, key=lambda p: p.get("odds", float("inf")))
        odds = best.get("odds")
        size_available = best.get("available-amount", best.get("available_amount"))
        if odds is None:
            continue
        candidates.append((runner, odds, size_available))

    if not candidates:
        return None

    # Favorite = shortest price (lowest odds) in the field.
    favorite_runner, odds, size_available = min(candidates, key=lambda c: c[1])

    if not (strategy["min_back_odds"] <= odds <= strategy["max_back_odds"]):
        return None

    min_liquidity = strategy.get("minimum_liquidity")
    if min_liquidity and size_available is not None and size_available < min_liquidity:
        return None

    return favorite_runner.get("id"), favorite_runner.get("name"), odds
