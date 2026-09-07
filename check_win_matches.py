#!/usr/bin/env python3
"""Pulls live Soccer events straight from Matchbook and shows every
Match Odds runner's back odds, so you can see with your own eyes if
data is coming in and whether anything would fall in the Win
strategy's 1.45-1.60 range.

Run from the project root, with .env available:

    python3 check_win_matches.py

Does not place any bets. Read-only.
"""

import sys
sys.path.insert(0, "src")

from dotenv import load_dotenv
load_dotenv()

from api_client import MatchbookClient

MIN_ODDS = 1.45
MAX_ODDS = 1.60
SPORT_ID_SOCCER = "15"

client = MatchbookClient()
if not client.login():
    print("Login failed. Check your .env file.")
    sys.exit(1)

data = client.get_live_events(sport_ids=SPORT_ID_SOCCER, per_page=30)

if not data or "events" not in data:
    print("No data came back from Matchbook at all. Login or API problem.")
    sys.exit(1)

events = data["events"]
print(f"Pulled {len(events)} Soccer event(s) from Matchbook.\n")

if not events:
    print("Matchbook returned zero events right now. Nothing to scan — try again later.")
    sys.exit(0)

found_any_in_range = False

for event in events:
    name = event.get("name", "Unknown")
    start = event.get("start", "?")

    match_odds_market = None
    for market in event.get("markets", []):
        if market.get("name") == "Match Odds":
            match_odds_market = market
            break

    if not match_odds_market:
        print(f"- {name} (start {start}) — no Match Odds market offered")
        continue

    line = f"- {name} (start {start}):"
    for runner in match_odds_market.get("runners", []):
        backs = [p for p in runner.get("prices", []) if p.get("side") == "back"]
        if not backs:
            continue
        best = min(backs, key=lambda p: p.get("odds", float("inf")))
        odds = best.get("odds")
        in_range = odds is not None and MIN_ODDS <= odds <= MAX_ODDS
        marker = " <-- IN RANGE" if in_range else ""
        if in_range:
            found_any_in_range = True
        line += f"  [{runner.get('name')} @ {odds}{marker}]"
    print(line)

print()
if found_any_in_range:
    print(f"At least one runner is in the {MIN_ODDS}-{MAX_ODDS} range right now.")
else:
    print(f"Nothing currently in the {MIN_ODDS}-{MAX_ODDS} range. That's just the market, not a bug.")
