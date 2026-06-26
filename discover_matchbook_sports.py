#!/usr/bin/env python3
"""
Discover all sports available on Matchbook by testing sport IDs.
"""

import os
from dotenv import load_dotenv
import requests

load_dotenv()

USERNAME = os.getenv("MATCHBOOK_USERNAME")
PASSWORD = os.getenv("MATCHBOOK_PASSWORD")

if not USERNAME or not PASSWORD:
    print("Error: MATCHBOOK_USERNAME and MATCHBOOK_PASSWORD not found in .env")
    exit(1)

# Login
print("Logging in...")
login_resp = requests.post(
    "https://api.matchbook.com/bpapi/rest/security/session",
    json={"username": USERNAME, "password": PASSWORD},
    headers={"content-type": "application/json"},
    timeout=15
)
login_resp.raise_for_status()
session_token = login_resp.json()["session-token"]
print("✓ Logged in\n")

headers = {
    "session-token": session_token,
    "accept": "application/json",
}

print("Testing sport IDs 1-50 to find available sports...\n")
sports_found = {}

for sport_id in range(1, 51):
    try:
        resp = requests.get(
            f"https://api.matchbook.com/edge/rest/events",
            params={"sport-ids": sport_id, "per-page": 1},
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            events = data.get("events", [])
            if events:
                # Found at least one event for this sport
                event = events[0]
                sport_name = event.get("sport-name", f"Sport {sport_id}")
                sports_found[sport_id] = sport_name
                print(f"✓ ID {sport_id:2d}: {sport_name}")
    except:
        pass

print("\n" + "="*50)
print("Summary:")
for sid, name in sorted(sports_found.items()):
    print(f"{sid}: {name}")
