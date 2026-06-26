#!/usr/bin/env python3
"""
Fetch all sports available on Matchbook API.
Reads credentials from .env file in current directory.
"""

import os
from dotenv import load_dotenv
import requests
import json

# Load .env file
load_dotenv()

USERNAME = os.getenv("MATCHBOOK_USERNAME")
PASSWORD = os.getenv("MATCHBOOK_PASSWORD")

if not USERNAME or not PASSWORD:
    print("Error: MATCHBOOK_USERNAME and MATCHBOOK_PASSWORD not found in .env file")
    exit(1)

# Login
print("Logging in...")
login_url = "https://api.matchbook.com/bpapi/rest/security/session"
login_resp = requests.post(
    login_url,
    json={"username": USERNAME, "password": PASSWORD},
    headers={"content-type": "application/json"},
    timeout=15
)
login_resp.raise_for_status()
session_token = login_resp.json()["session-token"]
print("✓ Logged in\n")

# Fetch sports - try multiple possible endpoints
print("Fetching sports...")
headers = {
    "session-token": session_token,
    "accept": "application/json",
}

endpoints = [
    "https://api.matchbook.com/edge/rest/sports",
    "https://api.matchbook.com/bpapi/rest/sports",
    "https://api.matchbook.com/edge/rest/events?per-page=1&sport-ids=1,2,3,4,5,15",  # Try to infer from events
]

sports = None
for endpoint in endpoints:
    try:
        print(f"Trying: {endpoint}")
        sports_resp = requests.get(endpoint, headers=headers, timeout=15)
        if sports_resp.status_code == 200:
            sports = sports_resp.json().get("sports", [])
            print(f"✓ Found sports at: {endpoint}\n")
            break
        else:
            print(f"  → {sports_resp.status_code}")
    except Exception as e:
        print(f"  → Error: {e}")

if not sports:
    print("\nCouldn't find sports endpoint. Matchbook API may not expose a sports list.")
    print("Try checking https://docs.matchbook.com for the correct endpoint.")
    exit(1)

print(f"Found {len(sports)} sports:\n")
print("=" * 80)

for sport in sorted(sports, key=lambda s: s.get("name", "")):
    print(f"Name: {sport.get('name')}")
    print(f"ID:   {sport.get('id')}")
    print(f"URL:  {sport.get('url')}")
    print(f"Other fields: {list(sport.keys())}")
    print("-" * 80)

# Also save to JSON file
with open("matchbook_sports.json", "w") as f:
    json.dump(sports, f, indent=2)
print(f"\nSaved to matchbook_sports.json")
