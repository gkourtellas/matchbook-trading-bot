"""Checks the Match Odds market for a trigger (Home or Away back odds in
range), then places the bet on the matching Double Chance runner from
the SAME event — not the Match Odds market itself.

FIX (2026-07-12): Matchbook does NOT guarantee that runner 0/1/2 in
Match Odds lines up with runner 0/1/2 in Double Chance for the same
team. The old code assumed fixed index positions and picked the wrong
team's Double Chance selection when the order differed (confirmed bug:
KFUM Oslo vs Bodo/Glimt bet on the wrong side). This version matches
runners by comparing team NAMES instead of trusting index order.

This is a normal back bet (unlike market_lay_opponent.py), so cash-out
works on it without any special math.
"""


def _best_back_odds(runner):
    backs = [p for p in runner.get("prices", []) if p.get("side") == "back"]
    if not backs:
        return None
    best = min(backs, key=lambda p: p.get("odds", float("inf")))
    return best.get("odds")


def find_opportunity_in_event(event, strategy):
    """Returns (runner_id, runner_name, odds, market_id) for the Double
    Chance runner to back, or None if no trigger / no Double Chance
    market is available for this event.
    """
    match_odds_market = None
    double_chance_market = None
    for market in event.get("markets", []):
        name = market.get("name")
        if name == "Match Odds":
            match_odds_market = market
        elif name == "Double Chance":
            double_chance_market = market

    if not match_odds_market or not double_chance_market:
        return None

    mo_runners = match_odds_market.get("runners", [])
    dc_runners = double_chance_market.get("runners", [])
    if len(mo_runners) < 2 or len(dc_runners) < 3:
        return None

    # Identify the Draw runner in Match Odds by name (not by index),
    # so we know which two runners are the actual teams.
    team_runners = [r for r in mo_runners if (r.get("name") or "").strip().lower() != "draw"]
    if len(team_runners) < 2:
        return None

    # Find whichever team runner's back odds fall in the strategy's range.
    trigger_runner = None
    for r in team_runners:
        odds = _best_back_odds(r)
        if odds is not None and strategy["min_back_odds"] <= odds <= strategy["max_back_odds"]:
            trigger_runner = r
            break

    if trigger_runner is None:
        return None

    trigger_name = (trigger_runner.get("name") or "").strip()
    if not trigger_name:
        return None

    # Find the Double Chance runner that covers "<trigger team> or Draw".
    # Match by NAME, not by position: it must contain the trigger team's
    # name AND the word "Draw" (this excludes "TeamA or TeamB" runners).
    target_runner = None
    for dc in dc_runners:
        dc_name = (dc.get("name") or "")
        if trigger_name in dc_name and "draw" in dc_name.lower():
            target_runner = dc
            break

    if target_runner is None:
        return None

    backs = [p for p in target_runner.get("prices", []) if p.get("side") == "back"]
    if not backs:
        return None

    best = min(backs, key=lambda p: p.get("odds", float("inf")))
    odds = best.get("odds")
    size_available = best.get("available-amount", best.get("available_amount"))

    if odds is None:
        return None

    min_liquidity = strategy.get("minimum_liquidity")
    if min_liquidity and size_available is not None and size_available < min_liquidity:
        return None

    return target_runner.get("id"), target_runner.get("name"), odds, double_chance_market.get("id")
