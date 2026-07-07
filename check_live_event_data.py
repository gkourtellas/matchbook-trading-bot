"""One-off check: dump full data for one LIVE match, so we can find
which field (if any) holds the match minute / time elapsed.

Run this while a match is actually live (in-play):
    python check_live_event_data.py

It logs in, scans Soccer (sport id 15) with NO state filter (so live
matches show up even if their state isn't "open"), finds the first
live event, and prints its full raw data plus every top-level key name.
"""

import sys
import json

sys.path.insert(0, "src")

from dotenv import load_dotenv
load_dotenv()

from api_client import MatchbookClient

client = MatchbookClient()
if not client.login():
    print("Login failed. Check your .env file.")
    sys.exit(1)

client.ensure_valid_session()
url = f"{client.base_url}/events"
params = {
    "sport-ids": "15",
    "include-prices": "true",
    "price-depth": 3,
    "price-mode": "expanded",
    "odds-type": "DECIMAL",
    "exchange-type": "back-lay",
    "per-page": 30,
}

import requests
response = requests.get(url, params=params, headers=client.headers)
if response.status_code == 401:
    if client.login():
        response = requests.get(url, params=params, headers=client.headers)

if response.status_code != 200:
    print(f"Request failed. Status: {response.status_code}, Response: {response.text}")
    sys.exit(1)

data = response.json()
events = data.get("events", [])

if not events:
    print("No Soccer events came back at all right now.")
    sys.exit(0)

print(f"Got {len(events)} event(s) back (no state filter).\n")
print("States seen on these events:")
for e in events:
    print(f"  - {e.get('name')}: state={e.get('state')}, in-play={e.get('in-play')}, live-execution={e.get('live-execution')}")

live_events = [e for e in events if e.get("in-play") or e.get("live-execution")]

if not live_events:
    print("\nNone of these events look live by in-play/live-execution flags.")
    print("Check the 'States seen' list above — if a live match shows a")
    print("different state name, that's the value we need.")
    sys.exit(0)

event = live_events[0]
print(f"\nFound {len(live_events)} live match(es). Showing first one:\n")
print(f"Match: {event.get('name')}\n")
print("Top-level keys on this event:")
for key in event.keys():
    print(f"  - {key}")
print("\nFull raw event data:")
print(json.dumps(event, indent=2))
