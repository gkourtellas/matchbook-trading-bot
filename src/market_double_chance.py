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

    # Identify the Draw runner in Match Odds by name, so we know which two runners are the teams.
    team_runners = [r for r in mo_runners if (r.get("name") or "").strip().lower() != "draw"]
    if len(team_runners) < 2:
        return None

    # Determine which team is the Favorite (lower back odds in Match Odds).
    team_with_odds = []
    for r in team_runners:
        odds = _best_back_odds(r)
        if odds is not None and odds > 1.0:
            team_with_odds.append((r, odds))

    if len(team_with_odds) < 2:
        return None

    team_with_odds.sort(key=lambda t: t[1])
    fav_runner, fav_mo_odds = team_with_odds[0]
    dog_runner, dog_mo_odds = team_with_odds[1]

    target_market = strategy.get("market_name", "Match Odds")
    min_odds = strategy.get("min_back_odds")
    max_odds = strategy.get("max_back_odds")

    # If target market is Match Odds, verify favorite's MATCH ODDS fall in range
    if target_market == "Match Odds":
        if min_odds is not None and fav_mo_odds < min_odds:
            return None
        if max_odds is not None and fav_mo_odds > max_odds:
            return None

    fav_name = (fav_runner.get("name") or "").strip()
    if not fav_name:
        return None

    # Find the Double Chance runner that covers "<favorite team> or Draw" (or "Draw or <favorite team>").
    # Matches by team name and requires "draw" to exclude "TeamA or TeamB" selections.
    target_runner = None
    for dc in dc_runners:
        dc_name = (dc.get("name") or "")
        if fav_name in dc_name and "draw" in dc_name.lower():
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

    if odds is None or odds <= 1.0:
        return None

    # If target market is Double Chance, verify DOUBLE CHANCE odds fall in range
    if target_market == "Double Chance":
        if min_odds is not None and odds < min_odds:
            return None
        if max_odds is not None and odds > max_odds:
            return None

    min_liquidity = strategy.get("minimum_liquidity")
    if min_liquidity and size_available is not None and size_available < min_liquidity:
        return None

    return target_runner.get("id"), target_runner.get("name"), odds, double_chance_market.get("id")
