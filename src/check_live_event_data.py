"""One-off check: dump full data for one LIVE match, so we can find
which field (if any) holds the match minute / time elapsed.

Run this while a match is actually live (in-play):
    python check_live_event_data.py

It logs in, scans Soccer (sport id 15), finds the first live event,
and prints its full raw data plus every top-level key name.
"""

import sys
import json
sys.path.insert(0, "src")

from api_client import MatchbookClient

client = MatchbookClient()
if not client.login():
    print("Login failed. Check your .env file.")
    sys.exit(1)

data = client.get_live_events(sport_ids="15", per_page=30)
if not data or "events" not in data:
    print("No data back from Matchbook.")
    sys.exit(1)

live_events = [e for e in data["events"] if e.get("in-play") or e.get("live-execution")]

if not live_events:
    print("No live (in-play) Soccer matches right now. Try again later during a live game.")
    sys.exit(0)

event = live_events[0]

print(f"Found {len(live_events)} live match(es). Showing first one:\n")
print(f"Match: {event.get('name')}\n")

print("Top-level keys on this event:")
for key in event.keys():
    print(f"  - {key}")

print("\nFull raw event data:")
print(json.dumps(event, indent=2))
