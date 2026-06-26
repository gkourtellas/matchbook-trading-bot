"""Finds a betting opportunity in a 'Match Odds' or 'Moneyline' market
(both are simple win/lose markets — same logic, different name per sport).
"""


def find_opportunity(market, strategy):
    """Returns (runner_id, runner_name, odds) if this market has a bet
    worth placing, otherwise None.
    """
    for runner in market.get("runners", []):
        prices = runner.get("prices", [])
        backs = [p for p in prices if p.get("side") == "back"]
        if not backs:
            continue

        odds = backs[0].get("odds")
        size_available = backs[0].get("available-amount", backs[0].get("available_amount"))

        if odds is None:
            continue
        if not (strategy["min_back_odds"] <= odds <= strategy["max_back_odds"]):
            continue

        min_liquidity = strategy.get("minimum_liquidity")
        if min_liquidity and size_available is not None and size_available < min_liquidity:
            continue

        return runner.get("id"), runner.get("name"), odds

    return None
