"""
One-off check: dumps meta-tags (and full event) for upcoming Horse Racing
events, so we can find which field/tag holds the country (US, Australia, etc).

Run from the project root, with .env available:

    python3 find_country_field.py

Does not place any bets. Read-only.
"""

import sys
import json

sys.path.insert(0, "src")

from dotenv import load_dotenv
load_dotenv()

from api_client import MatchbookClient

SPORT_ID_HORSE_RACING = "24735152712200"

client = MatchbookClient()
if not client.login():
    print("Login failed. Check your .env file.")
    sys.exit(1)

data = client.get_live_events(sport_ids=SPORT_ID_HORSE_RACING, per_page=10)

if not data or "events" not in data or not data["events"]:
    print("No Horse Racing events came back right now. Try again later.")
    sys.exit(0)

events = data["events"]
print(f"Got {len(events)} event(s). Showing meta-tags for each:\n")

for e in events:
    print("=" * 80)
    print(f"Event: {e.get('name')}")
    print("meta-tags:")
    print(json.dumps(e.get("meta-tags", []), indent=2))

print("\n" + "=" * 80)
print("Full raw data for the FIRST event (in case country isn't in meta-tags):")
print(json.dumps(events[0], indent=2))
