#!/usr/bin/env python3
"""Logs back-side liquidity for upcoming Soccer matches, over time, to a
CSV file — so you can look back later and decide what minimum_liquidity
cutoff actually makes sense for your strategies.

This does NOT place any bets. It only reads and logs.

Run it and leave it running (e.g. in a screen/tmux session, or as its
own docker service):

    python3 log_liquidity.py

Every POLL_INTERVAL_SECONDS it scans upcoming Soccer events and appends
one row per runner per market to config/liquidity_log.csv:

    timestamp, event_name, league, market_name, runner_name, odds, available_liquidity

Stop it with Ctrl+C. Safe to restart — it just keeps appending.
"""

import csv
import os
import sys
import time
from datetime import datetime, timezone




from api_client import MatchbookClient

SPORT_ID_SOCCER = "15"
POLL_INTERVAL_SECONDS = 300  # 5 minutes
OUTPUT_FILE = os.path.join("config", "liquidity_log.csv")
MARKETS_TO_LOG = {"Match Odds", "Total"}

FIELDNAMES = [
    "timestamp", "event_id", "event_name", "league",
    "market_name", "runner_name", "back_odds", "available_liquidity",
]


def extract_league(event):
    for tag in event.get("meta-tags", []):
        if tag.get("type") == "COMPETITION":
            return tag.get("name")
    return None


def ensure_file():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    is_new = not os.path.isfile(OUTPUT_FILE)
    if is_new:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def log_snapshot(client):
    data = client.get_live_events(sport_ids=SPORT_ID_SOCCER, per_page=50)
    if not data or "events" not in data:
        print("No data back from Matchbook this pass.")
        return 0

    now = datetime.now(timezone.utc).isoformat()
    rows = []

    for event in data["events"]:
        event_name = event.get("name", "Unknown")
        league = extract_league(event)

        for market in event.get("markets", []):
            market_name = market.get("name")
            if market_name not in MARKETS_TO_LOG:
                continue

            for runner in market.get("runners", []):
                backs = [p for p in runner.get("prices", []) if p.get("side") == "back"]
                if not backs:
                    continue
                best = min(backs, key=lambda p: p.get("odds", float("inf")))
                odds = best.get("odds")
                liquidity = best.get("available-amount", best.get("available_amount"))

                rows.append({
                    "timestamp": now,
                    "event_id": event.get("id"),
                    "event_name": event_name,
                    "league": league or "",
                    "market_name": market_name,
                    "runner_name": runner.get("name"),
                    "back_odds": odds,
                    "available_liquidity": liquidity,
                })

    if rows:
        with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writerows(rows)

    return len(rows)


def main():
    ensure_file()
    client = MatchbookClient()
    if not client.login():
        print("Login failed. Check your .env file.")
        sys.exit(1)

    print(f"Logging liquidity to {OUTPUT_FILE} every {POLL_INTERVAL_SECONDS}s. Ctrl+C to stop.")

    while True:
        try:
            count = log_snapshot(client)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Logged {count} row(s).")
        except Exception as e:
            print(f"⚠️ Error during snapshot: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
