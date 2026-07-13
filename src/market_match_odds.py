"""Finds a betting opportunity in a 'Match Odds' or 'Moneyline' market
(both are simple win/lose markets — same logic, different name per sport).

Filters added:
- min_field_size: skip market if fewer runners than this (team sports too)
- spread_cap_percent: skip runner if (lay-back)/back * 100 > cap (thin market)
"""


def find_opportunity(market, strategy):
    """Returns (runner_id, runner_name, odds) if this market has a bet
    worth placing, otherwise None.
    """
    runners = market.get("runners", [])

    min_field_size = strategy.get("min_field_size")
    if min_field_size and len(runners) < min_field_size:
        return None

    spread_cap = strategy.get("spread_cap_percent")

    for runner in runners:
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
