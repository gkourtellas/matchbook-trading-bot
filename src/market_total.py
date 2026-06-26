"""Finds a betting opportunity in a 'Total' (Over/Under) market.

Needs the strategy to say which line and direction to look for,
e.g. total_range "2.5" and total_direction "Over".
"""


def find_opportunity(market, strategy):
    """Returns (runner_id, runner_name, odds) if this market has a bet
    worth placing, otherwise None.
    """
    wanted_range = str(strategy.get("total_range", "")).strip()
    wanted_direction = str(strategy.get("total_direction", "")).strip().lower()

    for runner in market.get("runners", []):
        runner_name = (runner.get("name") or "")
        name_lower = runner_name.lower()

        if wanted_direction not in name_lower:
            continue
        if wanted_range not in runner_name:
            continue

        prices = runner.get("prices", [])
        backs = [p for p in prices if p.get("side") == "back"]
        if not backs:
            continue

        # Best back price = lowest odds available to back (not necessarily first in the list).
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

        return runner.get("id"), runner.get("name"), odds

    return None
