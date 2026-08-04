"""
Finds score / minute fields on a LIVE event automatically.
Run only while a match is actually in progress:

    python3 find_score_fields.py

Prints just the relevant bits, not the whole JSON.
"""

import sys
import json

sys.path.insert(0, "src")

from dotenv import load_dotenv
load_dotenv()

from api_client import MatchbookClient

KEYWORDS = ["score", "minute", "period", "clock", "elapsed", "time", "half"]


def hunt(obj, path=""):
    """Walk the whole event dict/list and print anything whose key
    name looks score/time related, at any depth."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            if any(word in k.lower() for word in KEYWORDS):
                found.append((new_path, v))
            found.extend(hunt(v, new_path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):  # only first few list items
            found.extend(hunt(v, f"{path}[{i}]"))
    return found


client = MatchbookClient()
if not client.login():
    print("Login failed. Check .env")
    sys.exit(1)

data = client.get_live_events(sport_ids="15", per_page=30)
if not data or "events" not in data:
    print("No data back from Matchbook.")
    sys.exit(1)

live = [e for e in data["events"] if e.get("in-running-flag")]
print(f"{len(live)} live event(s) found.\n")

if not live:
    print("No live match right now. Try again during a live game.")
    sys.exit(0)

event = live[0]
print(f"Match: {event.get('name')}\n")

matches = hunt(event)
if not matches:
    print("No score/minute-like fields found. Dumping top-level keys instead:")
    for k in event.keys():
        print(f"  - {k}")
else:
    print("Score/time-related fields found:")
    for path, val in matches:
        print(f"  {path} = {val}")
