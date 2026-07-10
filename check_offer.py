#!/usr/bin/env python3
"""One-off check: shows exactly what Matchbook has recorded for the
current open bet of one strategy — the REAL matched odds/status, not
what our own logs/dashboard show.

Run from the project root, with .env available:

    python3 check_offer.py "Fav_Backing_Dogs"

(use the exact strategy name as it appears in strategies.json)
"""

import json
import os
import re
import sys

sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()

from api_client import MatchbookClient

if len(sys.argv) < 2:
    print('Usage: python3 check_offer.py "Strategy Name"')
    sys.exit(1)

strategy_name = sys.argv[1]
safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", strategy_name.strip())
state_path = os.path.join("config", "state", f"{safe_name}.json")

if not os.path.isfile(state_path):
    print(f"No state file found at {state_path}.")
    sys.exit(1)

with open(state_path, encoding="utf-8") as f:
    state = json.load(f)

active_bets = state.get("active_bets", [])
if not active_bets:
    print("No active bets recorded for this strategy right now.")
    sys.exit(0)

client = MatchbookClient()
if not client.login():
    print("Login failed. Check your .env file.")
    sys.exit(1)

for bet in active_bets:
    offer_id = bet.get("offer_id")
    print("=" * 70)
    print(f"Our records — event: {bet.get('event_name')}")
    print(f"Our records — selection: {bet.get('selection_name')}")
    print(f"Our records — odds we THINK we got: {bet.get('odds')}")
    print(f"Our records — stake: {bet.get('stake')}")
    print(f"offer_id: {offer_id}")
    print("-" * 70)

    if not offer_id:
        print("No offer_id saved for this bet — can't look it up.")
        continue

    raw = client.get_order_status(offer_id)
    print("RAW response from Matchbook for this offer:")
    print(json.dumps(raw, indent=2))
